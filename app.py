#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import platform
import logging
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from collections import defaultdict
import traceback
import io
import base64
from werkzeug.exceptions import HTTPException
import requests

# screening_and_ai モジュールからインポート
from screening_and_ai import AIAnalyzer, process_enhanced_screening

# OSに応じたパス設定
def get_base_path():
    """OSに応じた適切なベースパスを返す"""
    if platform.system() == 'Windows':
        return Path(r'C:\Mcp\MergeApp_AI_2')
    else:
        # Linux/Ubuntu用のパス
        # 環境変数からベースパスを取得（デフォルトは現在のディレクトリ）
        base_path = os.environ.get('STOCK_APP_BASE_PATH', os.path.dirname(os.path.abspath(__file__)))
        return Path(base_path)

# ベースパスの設定
BASE_PATH = get_base_path()

# ディレクトリ構造の自動作成
def setup_directories():
    """必要なディレクトリを作成"""
    directories = [
        BASE_PATH / 'app',
        BASE_PATH / 'app' / 'templates',
        BASE_PATH / 'app' / 'static',
        BASE_PATH / 'app' / 'static' / 'js',
        BASE_PATH / 'app' / 'static' / 'css',
        BASE_PATH / 'logs'
    ]
    
    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # Ubuntuでの権限設定
            if platform.system() != 'Windows':
                os.chmod(str(directory), 0o755)
            print(f"ディレクトリを確認/作成: {directory}")
        except Exception as e:
            print(f"ディレクトリ作成エラー {directory}: {e}")

# ディレクトリのセットアップ
setup_directories()

# ログ設定
log_file = BASE_PATH / 'logs' / 'app.log'
try:
    # ログファイルのディレクトリが存在することを確認
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # ログハンドラーの設定
    handlers = []
    
    # ファイルハンドラー（エラーハンドリング付き）
    try:
        file_handler = logging.FileHandler(str(log_file), encoding='utf-8')
        handlers.append(file_handler)
    except Exception as e:
        print(f"ログファイルハンドラー作成エラー: {e}")
    
    # コンソールハンドラー
    handlers.append(logging.StreamHandler(sys.stdout))
    
    # ログ設定
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers
    )
    
except Exception as e:
    print(f"ログ設定エラー: {e}")
    # 最小限のコンソールログ設定
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

logger = logging.getLogger(__name__)

# Flaskアプリケーションの作成
app = Flask(__name__, 
          template_folder=str(BASE_PATH / 'app' / 'templates'),
          static_folder=str(BASE_PATH / 'app' / 'static'))

# テンプレートとスタティックフォルダの確認
logger.info(f"テンプレートフォルダ: {app.template_folder}")
logger.info(f"スタティックフォルダ: {app.static_folder}")

# セキュリティ設定
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# 本番環境判定
is_production = os.environ.get('FLASK_ENV', 'development') == 'production'

if is_production:
    app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS環境では必須
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
else:
    # 開発環境では緩和した設定
    app.config['SESSION_COOKIE_SECURE'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# CORS設定（本番環境では特定のオリジンのみ許可）
allowed_origins = os.environ.get('ALLOWED_ORIGINS', '*').split(',')
CORS(app, origins=allowed_origins)

# データベースパス（環境変数で指定可能）
DB_PATH = Path(os.environ.get('STOCK_DB_PATH', str(BASE_PATH / 'stock_database.sqlite3')))

# データベースファイルの存在確認
if not DB_PATH.exists():
    logger.warning(f"データベースファイルが見つかりません: {DB_PATH}")
    # データベースファイルの検索
    possible_paths = [
        BASE_PATH / 'stock_database.sqlite3',
        Path.cwd() / 'stock_database.sqlite3',
        Path('/var/lib/stock_app/stock_database.sqlite3'),  # Ubuntu標準パス
    ]
    
    for path in possible_paths:
        if path.exists():
            DB_PATH = path
            logger.info(f"データベースファイルを発見: {DB_PATH}")
            break
    else:
        logger.error("データベースファイルが見つかりません。アプリケーションを終了します。")
        sys.exit(1)

# グローバル変数
stock_data_repository = None
stock_analyzer = None
chart_service = None
stock_service = None
sector_analyzer = None
ai_analyzer = None

# 必要なクラスの定義
class DatabaseConnector:
    def __init__(self, db_path):
        self.db_path = str(db_path)
        logger.info(f"データベースコネクタを初期化: {self.db_path}")
        # データベースファイルの読み取り権限を確認
        if not os.access(self.db_path, os.R_OK):
            raise PermissionError(f"データベースファイルに読み取り権限がありません: {self.db_path}")
        
    def get_connection(self):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # 結果を辞書形式で取得
            return conn
        except sqlite3.Error as e:
            logger.error(f"データベース接続エラー: {e}")
            raise
        
    def execute_query(self, query, params=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                return cursor.fetchall()
            except sqlite3.Error as e:
                logger.error(f"データベースクエリエラー: {str(e)}")
                logger.error(f"クエリ: {query}")
                logger.error(f"パラメータ: {params}")
                raise

class StockDataRepository:
    def __init__(self, db_connector):
        self.db_connector = db_connector
        logger.info("株価データリポジトリを初期化しました")
        
    def get_latest_stock_data(self):
        query = """
        SELECT 
            code,
            name,
            date,
            price AS close,
            volume,
            market_cap,
            per,
            pbr,
            CASE 
                WHEN eps != 0 AND bps != 0 THEN (eps / bps * 100)
                ELSE NULL
            END AS roe,
            industry AS sector,
            industry,
            market,
            margin_buying AS credit_balance,
            margin_buying AS margin_balance,
            margin_selling AS credit_sell_balance,
            margin_selling AS margin_sell_balance,
            CASE 
                WHEN margin_buying > 0 THEN margin_ratio
                ELSE NULL
            END AS credit_ratio,
            margin_ratio,
            CASE 
                WHEN margin_buying IS NOT NULL OR margin_selling IS NOT NULL THEN 1
                ELSE 0
            END AS is_credit_issue,
            NULL AS credit_start_date,
            vwap
        FROM stock_database
        WHERE date = (SELECT MAX(date) FROM stock_database)
        """
        return self.db_connector.execute_query(query)
        
    def get_stock_history(self, code, days=30):
        query = """
        SELECT 
            date,
            price AS close,
            volume,
            high_price AS high,
            low_price AS low,
            open_price AS open,
            vwap
        FROM stock_database
        WHERE code = ?
        AND date >= date('now', '-' || ? || ' days')
        ORDER BY date DESC
        """
        return self.db_connector.execute_query(query, (code, days))
    
    def get_stock_info(self, code):
        """特定銘柄の最新情報を取得"""
        query = """
        SELECT 
            code,
            name,
            date,
            price,
            change_amount,
            change_percent,
            volume,
            market
        FROM stock_database
        WHERE code = ?
        AND date = (SELECT MAX(date) FROM stock_database)
        """
        result = self.db_connector.execute_query(query, (code,))
        if result:
            row = result[0]
            return {
                'code': row[0],
                'name': row[1],
                'date': row[2],
                'price': row[3],
                'change': row[4],
                'change_percent': row[5],
                'volume': row[6],
                'market': row[7]
            }
        return None

class StockAnalyzer:
    def __init__(self, stock_data_repo):
        self.stock_data_repo = stock_data_repo
        logger.info("株価アナライザを初期化しました")
        
    def calculate_technical_indicators(self, df):
        """テクニカル指標を計算"""
        if len(df) < 5:
            return df
            
        # 移動平均
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma25'] = df['close'].rolling(window=25).mean()
        df['ma50'] = df['close'].rolling(window=50).mean()
        df['ma75'] = df['close'].rolling(window=75).mean()
        
        # ボリンジャーバンド
        df['bb_middle'] = df['ma20']
        std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (std * 2)
        df['bb_lower'] = df['bb_middle'] - (std * 2)
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['histogram'] = df['macd'] - df['signal']
        
        # 出来高移動平均
        df['volume_ma5'] = df['volume'].rolling(window=5).mean()
        df['volume_ma20'] = df['volume'].rolling(window=20).mean()
        
        return df

class ChartService:
    def __init__(self, stock_analyzer):
        self.stock_analyzer = stock_analyzer
        logger.info("チャートサービスを初期化しました")
        
    def generate_chart_data(self, code):
        """チャートデータを生成（HTMLテンプレートが期待する形式）"""
        try:
            # 銘柄情報を取得
            stock_info = self.stock_analyzer.stock_data_repo.get_stock_info(code)
            if not stock_info:
                logger.warning(f"銘柄情報が見つかりません: {code}")
                return None
            
            # 過去120日分のデータを取得（4か月間）
            history = self.stock_analyzer.stock_data_repo.get_stock_history(code, 120)
            if not history:
                logger.warning(f"価格履歴が見つかりません: {code}")
                return None
                
            # DataFrameに変換
            df = pd.DataFrame(history, columns=['date', 'close', 'volume', 'high', 'low', 'open', 'vwap'])
            df = df.sort_values('date')  # 日付順にソート
            
            # テクニカル指標を計算
            df = self.stock_analyzer.calculate_technical_indicators(df)
            
            # チャートデータの構築（HTMLテンプレートが期待する形式）
            chart_data = {
                'stock_info': {
                    'price': float(stock_info['price']) if stock_info['price'] else 0,
                    'change': float(stock_info['change']) if stock_info['change'] else 0,
                    'change_percent': float(stock_info['change_percent']) if stock_info['change_percent'] else 0,
                    'last_update': stock_info['date']
                },
                
                # ローソク足データ
                'candlestick': [{
                    'date': row['date'],
                    'open': float(row['open']) if row['open'] else 0,
                    'high': float(row['high']) if row['high'] else 0,
                    'low': float(row['low']) if row['low'] else 0,
                    'close': float(row['close']) if row['close'] else 0
                } for _, row in df.iterrows()],
                
                # 出来高データ
                'volume': [{
                    'date': row['date'],
                    'volume': int(row['volume']) if row['volume'] else 0,
                    'color': '#00B050' if idx > 0 and row['close'] >= df.iloc[idx-1]['close'] else '#FF0000'
                } for idx, row in df.iterrows()],
                
                # 移動平均線データ
                'line_chart': {
                    'dates': df['date'].tolist(),
                    'series': [
                        {
                            'name': 'stock_price',
                            'data': [float(v) if pd.notna(v) else None for v in df['close']]
                        },
                        {
                            'name': 'moving_average_5day',
                            'data': [float(v) if pd.notna(v) else None for v in df['ma5']]
                        },
                        {
                            'name': 'moving_average_25day',
                            'data': [float(v) if pd.notna(v) else None for v in df['ma25']]
                        },
                        {
                            'name': 'moving_average_50day',
                            'data': [float(v) if pd.notna(v) else None for v in df['ma50']]
                        },
                        {
                            'name': 'moving_average_75day',
                            'data': [float(v) if pd.notna(v) else None for v in df['ma75']]
                        }
                    ]
                },
                
                # 5日移動・加重平均ゴールデンクロス
                'ma_golden_cross': {
                    'dates': df['date'].tolist(),
                    'series': [
                        {
                            'name': '株価',
                            'data': [float(v) if pd.notna(v) else None for v in df['close']],
                            'color': '#0066CC'
                        },
                        {
                            'name': 'VWAP',
                            'data': [float(v) if pd.notna(v) else None for v in df['vwap']],
                            'color': '#FF6600'
                        },
                        {
                            'name': '5日移動平均',
                            'data': [float(v) if pd.notna(v) else None for v in df['ma5']],
                            'color': '#00CC00'
                        },
                        {
                            'name': '5日出来高移動平均',
                            'data': [float(v) if pd.notna(v) else None for v in df['volume_ma5']],
                            'color': '#00AA00'
                        },
                        {
                            'name': '5日出来高加重移動平均',
                            'data': [float(v) if pd.notna(v) else None for v in df['volume_ma20']],
                            'color': '#CC00CC'
                        }
                    ]
                },
                
                # ボリンジャーバンド
                'bollinger_bands': {
                    'dates': df['date'].tolist(),
                    'series': [
                        {
                            'name': 'upper_band',
                            'data': [float(v) if pd.notna(v) else None for v in df['bb_upper']]
                        },
                        {
                            'name': 'middle_band',
                            'data': [float(v) if pd.notna(v) else None for v in df['bb_middle']]
                        },
                        {
                            'name': 'lower_band',
                            'data': [float(v) if pd.notna(v) else None for v in df['bb_lower']]
                        }
                    ]
                },
                
                # RSI
                'rsi': {
                    'dates': df['date'].tolist(),
                    'series': [{
                        'name': 'RSI',
                        'data': [float(v) if pd.notna(v) else None for v in df['rsi']]
                    }]
                },
                
                # MACD
                'macd': {
                    'dates': df['date'].tolist(),
                    'series': [
                        {
                            'name': 'MACD',
                            'data': [float(v) if pd.notna(v) else None for v in df['macd']]
                        },
                        {
                            'name': 'Signal',
                            'data': [float(v) if pd.notna(v) else None for v in df['signal']]
                        },
                        {
                            'name': 'Histogram',
                            'data': [float(v) if pd.notna(v) else None for v in df['histogram']]
                        }
                    ]
                },
                
                # テクニカル指標（最新値）
                'technical': {
                    'indicators': {
                        'rsi': float(df['rsi'].iloc[-1]) if pd.notna(df['rsi'].iloc[-1]) else None,
                        'macd': float(df['macd'].iloc[-1]) if pd.notna(df['macd'].iloc[-1]) else None,
                        'signal': float(df['signal'].iloc[-1]) if pd.notna(df['signal'].iloc[-1]) else None,
                        'bollinger_bands': {
                            'upper': float(df['bb_upper'].iloc[-1]) if pd.notna(df['bb_upper'].iloc[-1]) else None,
                            'middle': float(df['bb_middle'].iloc[-1]) if pd.notna(df['bb_middle'].iloc[-1]) else None,
                            'lower': float(df['bb_lower'].iloc[-1]) if pd.notna(df['bb_lower'].iloc[-1]) else None
                        },
                        'price': float(df['close'].iloc[-1]) if pd.notna(df['close'].iloc[-1]) else None,
                        'price_above_ma25': bool(df['close'].iloc[-1] > df['ma25'].iloc[-1]) if pd.notna(df['ma25'].iloc[-1]) else None,
                        'price_above_ma50': bool(df['close'].iloc[-1] > df['ma50'].iloc[-1]) if pd.notna(df['ma50'].iloc[-1]) else None,
                        'price_above_ma75': bool(df['close'].iloc[-1] > df['ma75'].iloc[-1]) if pd.notna(df['ma75'].iloc[-1]) else None,
                        'volume_ratio': float(df['volume'].iloc[-1] / df['volume_ma20'].iloc[-1]) if pd.notna(df['volume_ma20'].iloc[-1]) and df['volume_ma20'].iloc[-1] > 0 else None
                    }
                }
            }
            
            return chart_data
            
        except Exception as e:
            logger.error(f"チャートデータ生成エラー: {str(e)}")
            logger.error(traceback.format_exc())
            return None

class StockService:
    def __init__(self, stock_data_repo, stock_analyzer, chart_service):
        self.stock_data_repo = stock_data_repo
        self.stock_analyzer = stock_analyzer
        self.chart_service = chart_service
        logger.info("株価サービスを初期化しました")
        
    def get_all_stocks(self):
        """全銘柄データを取得"""
        try:
            stocks = self.stock_data_repo.get_latest_stock_data()
            
            stock_list = []
            for stock in stocks:
                stock_dict = {
                    'code': stock[0],
                    'name': stock[1],
                    'date': stock[2],
                    'close': stock[3],  # price AS close
                    'volume': stock[4],
                    'market_cap': stock[5],
                    'per': stock[6],
                    'pbr': stock[7],
                    'roe': stock[8],
                    'sector': stock[9],
                    'industry': stock[10],
                    'market': stock[11],
                    'credit_balance': stock[12],
                    'margin_balance': stock[13],
                    'credit_sell_balance': stock[14],
                    'margin_sell_balance': stock[15],
                    'credit_ratio': stock[16],
                    'margin_ratio': stock[17],
                    'is_credit_issue': stock[18],
                    'credit_start_date': stock[19],
                    'vwap': stock[20] if len(stock) > 20 else None
                }
                stock_list.append(stock_dict)
                
            return stock_list
        except Exception as e:
            logger.error(f"株価データ取得エラー: {str(e)}")
            logger.error(traceback.format_exc())
            return []

class SectorAnalyzer:
    def __init__(self, stock_data_repo):
        self.stock_data_repo = stock_data_repo
        logger.info("セクターアナライザを初期化しました")
        
    def get_sector_performance(self):
        """セクター別パフォーマンスを取得"""
        query = """
        SELECT 
            industry AS sector,
            COUNT(*) as stock_count,
            AVG(CAST(REPLACE(REPLACE(per, '倍', ''), '-', '') AS REAL)) as avg_per,
            AVG(CAST(REPLACE(REPLACE(pbr, '倍', ''), '-', '') AS REAL)) as avg_pbr,
            AVG(CASE 
                WHEN eps != 0 AND bps != 0 THEN (eps / bps * 100)
                ELSE NULL
            END) as avg_roe,
            SUM(market_cap) as total_market_cap
        FROM stock_database
        WHERE date = (SELECT MAX(date) FROM stock_database)
        AND industry IS NOT NULL
        GROUP BY industry
        """
        return self.stock_data_repo.db_connector.execute_query(query)

# 初期化関数
def initialize_services():
    global stock_data_repository, stock_analyzer, chart_service, stock_service, sector_analyzer, ai_analyzer
    
    try:
        db_connector = DatabaseConnector(DB_PATH)
        stock_data_repository = StockDataRepository(db_connector)
        stock_analyzer = StockAnalyzer(stock_data_repository)
        chart_service = ChartService(stock_analyzer)
        stock_service = StockService(stock_data_repository, stock_analyzer, chart_service)
        sector_analyzer = SectorAnalyzer(stock_data_repository)
        ai_analyzer = AIAnalyzer(stock_data_repository)
        logger.info("全サービスの初期化が完了しました")
    except Exception as e:
        logger.error(f"サービス初期化エラー: {str(e)}")
        logger.error(traceback.format_exc())
        raise

# エラーハンドラー
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'ページが見つかりません'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"内部エラー: {str(error)}")
    return jsonify({'error': 'サーバー内部エラーが発生しました'}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    logger.error(f"未処理の例外: {str(e)}")
    logger.error(traceback.format_exc())
    return jsonify({'error': 'エラーが発生しました'}), 500

# アプリケーション起動時の初期化
try:
    initialize_services()
except Exception as e:
    logger.error(f"アプリケーション初期化失敗: {e}")
    # 初期化に失敗してもアプリケーションは起動させる（ヘルスチェック用）

# ルート定義
@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"テンプレートレンダリングエラー: {e}")
        return "<h1>株価分析システム</h1><p>システムを起動中です...</p>", 200

@app.route('/enhanced')
def enhanced_index():
    try:
        # テンプレート名のリスト（優先順位順）
        template_names = [
            'index_with_enhanced_screening_vgc_fixed_with_vwap_margin_lending.html',
            'index_enhanced.html',
            'index.html'
        ]
        
        # 利用可能なテンプレートを探す
        for template_name in template_names:
            template_path = Path(app.template_folder) / template_name
            if template_path.exists():
                logger.info(f"テンプレートを使用: {template_name}")
                return render_template(template_name)
        
        # テンプレートが見つからない場合
        logger.error("拡張版テンプレートが見つかりません")
        return jsonify({'error': 'テンプレートが見つかりません'}), 404
        
    except Exception as e:
        logger.error(f"拡張版テンプレートレンダリングエラー: {str(e)}")
        logger.error(traceback.format_exc())
        # エラーでも基本的なレスポンスを返す
        return "<h1>株価分析システム</h1><p>テンプレートの読み込みに失敗しました。</p>", 200

# チャートページのルート（修正版：両方のパスに対応）
@app.route('/stock/<code>/chart')
@app.route('/chart/<code>')  # JavaScript側が使用しているURL形式にも対応
def stock_chart(code):
    """銘柄のチャートページを表示"""
    try:
        if stock_data_repository is None:
            return render_template('error.html', error='サービスが初期化されていません'), 503
        
        # 銘柄情報を取得
        stock_info = stock_data_repository.get_stock_info(code)
        if not stock_info:
            return render_template('error.html', error='銘柄が見つかりません'), 404
        
        return render_template('chart_with_technical_indicators.html', 
                             stock_code=code, 
                             stock_name=stock_info.get('name', ''))
    except Exception as e:
        logger.error(f"チャートページエラー: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', error='チャートページの読み込みに失敗しました'), 500

# AI分析ページのルート（新規追加）
@app.route('/stock/<code>/ai-analysis')
@app.route('/ai-analysis/<code>')
def ai_analysis_page(code):
    """AI分析ページを表示"""
    try:
        if stock_data_repository is None:
            return render_template('error.html', error='サービスが初期化されていません'), 503
        
        # 銘柄情報を取得
        stock_info = stock_data_repository.get_stock_info(code)
        if not stock_info:
            return render_template('error.html', error='銘柄が見つかりません'), 404
        
        # AI分析テンプレートが存在するか確認
        template_path = Path(app.template_folder) / 'ai_analysis.html'
        if template_path.exists():
            return render_template('ai_analysis.html', 
                                 stock_code=code, 
                                 stock_name=stock_info.get('name', ''))
        else:
            # テンプレートがない場合は、JSONでAI分析結果を返す
            analysis_result = ai_analyzer.analyze_stock(code)
            return jsonify(analysis_result)
            
    except Exception as e:
        logger.error(f"AI分析ページエラー: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', error='AI分析ページの読み込みに失敗しました'), 500

# AI分析APIエンドポイント（新規追加）
@app.route('/api/stocks/<code>/ai-analysis')
def get_ai_analysis(code):
    """指定銘柄のAI分析を取得"""
    try:
        if ai_analyzer is None:
            return jsonify({
                'error': 'AI分析サービスが初期化されていません',
                'status': 'error'
            }), 503
            
        result = ai_analyzer.analyze_stock(code)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"AI分析APIエラー: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': 'AI分析の実行に失敗しました',
            'details': str(e),
            'status': 'error'
        }), 500

@app.route('/api/stocks')
def get_stocks():
    try:
        if stock_service is None:
            return jsonify({'error': 'サービスが初期化されていません'}), 503
            
        stocks = stock_service.get_all_stocks()
        # JavaScriptが期待する形式でレスポンスを返す
        return jsonify({
            'data': stocks,
            'count': len(stocks),
            'status': 'success'
        })
    except Exception as e:
        logger.error(f"株価データ取得エラー: {str(e)}")
        return jsonify({'error': 'データの取得に失敗しました'}), 500

# チャートAPIエンドポイント（修正版）
@app.route('/api/stocks/<code>/chart')
def get_stock_chart(code):
    """株価チャートデータを取得（修正版）"""
    try:
        if chart_service is None:
            return jsonify({
                'error': 'サービスが初期化されていません',
                'status': 'error'
            }), 503
            
        chart_data = chart_service.generate_chart_data(code)
        if chart_data:
            # JavaScriptが期待する形式でレスポンスを返す
            return jsonify({
                'status': 'success',
                'data': chart_data
            })
        else:
            return jsonify({
                'error': 'チャートデータが見つかりません',
                'status': 'error'
            }), 404
    except Exception as e:
        logger.error(f"チャートデータ取得エラー: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': 'チャートデータの取得に失敗しました',
            'details': str(e),
            'status': 'error'
        }), 500

@app.route('/api/sectors/performance')
def get_sector_performance():
    try:
        if sector_analyzer is None:
            return jsonify({'error': 'サービスが初期化されていません'}), 503
            
        performance = sector_analyzer.get_sector_performance()
        result = []
        for row in performance:
            result.append({
                'sector': row[0],
                'stock_count': row[1],
                'avg_per': row[2],
                'avg_pbr': row[3],
                'avg_roe': row[4],
                'total_market_cap': row[5]
            })
        return jsonify(result)
    except Exception as e:
        logger.error(f"セクターパフォーマンス取得エラー: {str(e)}")
        return jsonify({'error': 'セクターデータの取得に失敗しました'}), 500

# API キーの確認
def check_api_keys():
    deepseek_key = os.getenv('DEEPSEEK_API_KEY')
    if not deepseek_key:
        logger.warning("DEEPSEEK_API_KEY が設定されていません")
    return deepseek_key is not None

# 追加のAPIエンドポイント
@app.route('/api/available-dates')
def get_available_dates():
    """利用可能な日付を取得"""
    try:
        if stock_data_repository is None:
            return jsonify({'error': 'サービスが初期化されていません'}), 503
            
        query = """
        SELECT DISTINCT date 
        FROM stock_database 
        ORDER BY date DESC
        """
        dates = stock_data_repository.db_connector.execute_query(query)
        # JavaScript側の期待する形式に合わせる
        return jsonify({
            'dates': [date[0] for date in dates],
            'status': 'success'
        })
    except Exception as e:
        logger.error(f"日付取得エラー: {str(e)}")
        return jsonify({'error': '日付データの取得に失敗しました'}), 500

@app.route('/api/data-count-by-date')
def get_data_count_by_date():
    """日付別データ件数を取得"""
    try:
        if stock_data_repository is None:
            return jsonify({'error': 'サービスが初期化されていません'}), 503
            
        target_date = request.args.get('date')
        
        if target_date:
            # 特定の日付のデータ件数を取得
            query = """
            SELECT 
                (SELECT COUNT(*) FROM stock_database WHERE date = ?) as stock_count,
                (SELECT COUNT(*) FROM stock_indicators WHERE date = ?) as indicator_count
            """
            result = stock_data_repository.db_connector.execute_query(query, (target_date, target_date))
            if result:
                return jsonify({
                    'stock_count': result[0][0] or 0,
                    'indicator_count': result[0][1] or 0,
                    'status': 'success'
                })
        else:
            # 日付別のデータ件数一覧を取得
            query = """
            SELECT date, COUNT(*) as count
            FROM stock_database
            GROUP BY date
            ORDER BY date DESC
            """
            results = stock_data_repository.db_connector.execute_query(query)
            return jsonify([{'date': row[0], 'count': row[1]} for row in results])
    except Exception as e:
        logger.error(f"データ件数取得エラー: {str(e)}")
        return jsonify({'error': 'データ件数の取得に失敗しました'}), 500

@app.route('/api/latest-data-date')
def get_latest_data_date():
    """最新のデータ日付を取得"""
    try:
        if stock_data_repository is None:
            return jsonify({'error': 'サービスが初期化されていません'}), 503
            
        query = """
        SELECT MAX(date) as latest_date, COUNT(*) as count
        FROM stock_database
        WHERE date = (SELECT MAX(date) FROM stock_database)
        """
        result = stock_data_repository.db_connector.execute_query(query)
        if result and result[0] and result[0][0]:
            return jsonify({
                'latest_date': result[0][0],
                'count': result[0][1],
                'status': 'success'
            })
        else:
            return jsonify({'error': 'データが見つかりません'}), 404
    except Exception as e:
        logger.error(f"最新日付取得エラー: {str(e)}")
        return jsonify({'error': '最新日付の取得に失敗しました'}), 500

@app.route('/api/enhanced-screening')
def enhanced_screening():
    """拡張スクリーニング"""
    try:
        if stock_data_repository is None:
            return jsonify({'error': 'サービスが初期化されていません'}), 503
            
        # screening_and_ai モジュールの関数を使用
        stocks = process_enhanced_screening(stock_data_repository, request.args)
        
        # JavaScriptが期待する形式でレスポンスを返す
        return jsonify({
            'data': stocks,
            'count': len(stocks),
            'status': 'success'
        })
        
    except Exception as e:
        logger.error(f"拡張スクリーニングエラー: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': 'スクリーニングの実行に失敗しました',
            'details': str(e),
            'status': 'error'
        }), 500

# AI分析ページのルート（スクリーニング結果全体用）を追加
@app.route('/ai-analysis')
def ai_analysis_general():
    """AI分析ページを表示（スクリーニング結果全体用）"""
    try:
        return render_template('ai_analysis.html')
    except Exception as e:
        logger.error(f"AI分析ページエラー: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', error='AI分析ページの読み込みに失敗しました'), 500

# AI分析APIエンドポイント（スクリーニング結果全体用）を追加
@app.route('/api/ai-analyze', methods=['POST'])
def ai_analyze_screening_results():
    """スクリーニング結果全体のAI分析を実行"""
    try:
        if ai_analyzer is None:
            return jsonify({
                'success': False,
                'message': 'AI分析サービスが初期化されていません'
            }), 503
            
        data = request.get_json()
        query = data.get('query', '')
        screening_results = data.get('screening_results', [])
        include_chart_data = data.get('include_chart_data', False)
        
        if not query:
            return jsonify({
                'success': False,
                'message': '質問を入力してください'
            }), 400
            
        if not screening_results:
            return jsonify({
                'success': False,
                'message': 'スクリーニング結果がありません'
            }), 400
        
        # AI分析を実行
        analysis = ai_analyzer.analyze_screening_results(
            query, 
            screening_results,
            include_chart_data
        )
        
        return jsonify({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        logger.error(f"AI分析APIエラー: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': 'AI分析の実行に失敗しました'
        }), 500

# AI接続状態確認APIエンドポイントを追加
@app.route('/api/check-ai-status')
def check_ai_status():
    """AI APIの接続状態を確認"""
    try:
        api_key = os.environ.get('DEEPSEEK_API_KEY')
        
        if not api_key:
            return jsonify({
                'connected': False,
                'message': 'API未設定（デモモード）'
            })
        
        # 簡単な接続テスト（実際のAPIコールは行わない）
        return jsonify({
            'connected': True,
            'message': 'API接続可能'
        })
        
    except Exception as e:
        logger.error(f"AI状態確認エラー: {str(e)}")
        return jsonify({
            'connected': False,
            'message': 'API接続エラー'
        })

@app.route('/health')
def health_check():
    """ヘルスチェックエンドポイント"""
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'database': 'unknown',
            'stock_service': 'unknown',
            'chart_service': 'unknown',
            'sector_analyzer': 'unknown',
            'ai_analyzer': 'unknown'
        }
    }
    
    # サービスの状態をチェック
    try:
        if stock_data_repository and stock_data_repository.db_connector:
            # 簡単なクエリでデータベース接続を確認
            stock_data_repository.db_connector.execute_query("SELECT 1")
            health_status['services']['database'] = 'healthy'
    except Exception as e:
        health_status['services']['database'] = 'unhealthy'
        logger.error(f"データベースヘルスチェック失敗: {e}")
    
    health_status['services']['stock_service'] = 'healthy' if stock_service else 'not_initialized'
    health_status['services']['chart_service'] = 'healthy' if chart_service else 'not_initialized'
    health_status['services']['sector_analyzer'] = 'healthy' if sector_analyzer else 'not_initialized'
    health_status['services']['ai_analyzer'] = 'healthy' if ai_analyzer else 'not_initialized'
    
    # 全体のステータスを判定
    if any(status == 'unhealthy' or status == 'not_initialized' 
           for status in health_status['services'].values()):
        health_status['status'] = 'degraded'
    
    return jsonify(health_status)

# システム情報エンドポイント
@app.route('/api/system-info')
def system_info():
    """システム情報を取得"""
    return jsonify({
        'platform': platform.system(),
        'platform_version': platform.version(),
        'python_version': sys.version,
        'base_path': str(BASE_PATH),
        'db_path': str(DB_PATH),
        'template_folder': app.template_folder,
        'static_folder': app.static_folder,
        'environment': os.environ.get('FLASK_ENV', 'development'),
        'ai_enabled': bool(os.environ.get('DEEPSEEK_API_KEY'))
    })

# メイン実行部分
if __name__ == '__main__':
    logger.info("="*60)
    logger.info("株価分析システム Ubuntu対応版 v7 (AI分析機能付き) 起動")
    logger.info(f"Python バージョン: {sys.version}")
    logger.info(f"プラットフォーム: {platform.system()} {platform.version()}")
    logger.info(f"ベースパス: {BASE_PATH}")
    logger.info(f"データベースパス: {DB_PATH}")
    logger.info("="*60)
    
    # API キーの確認
    check_api_keys()
    
    # 環境に応じた起動設定
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', '5000'))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    if debug:
        logger.info(f"開発モードで起動: http://{host}:{port}")
        app.run(host=host, port=port, debug=True)
    else:
        # 本番環境では Gunicorn を使用することを推奨
        logger.info("本番環境モード")
        logger.info(f"推奨起動コマンド: gunicorn -w 4 -b {host}:{port} app:app")
        logger.info(f"または環境変数を設定:")
        logger.info(f"  export STOCK_APP_BASE_PATH=/path/to/app")
        logger.info(f"  export STOCK_DB_PATH=/path/to/database.sqlite3")
        logger.info(f"  export FLASK_ENV=production")
        logger.info(f"  export SECRET_KEY=your-secret-key")
        logger.info(f"  export ALLOWED_ORIGINS=https://yourdomain.com")
        logger.info(f"  export DEEPSEEK_API_KEY=your-api-key  # AI分析を有効にする場合")
        #app.run(host=host, port=port, debug=False)