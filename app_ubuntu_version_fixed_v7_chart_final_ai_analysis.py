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

class AIAnalyzer:
    """AI分析機能を提供するクラス"""
    def __init__(self, stock_data_repo):
        self.stock_data_repo = stock_data_repo
        self.api_key = os.environ.get('DEEPSEEK_API_KEY')
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        if self.api_key:
            logger.info(f"AIアナライザを初期化しました (APIキー: {self.api_key[:10]}...)")
        else:
            logger.info("AIアナライザを初期化しました (デモモード)")
    
    def analyze_stock(self, code):
        """指定された銘柄のAI分析を実行"""
        try:
            # 銘柄の詳細情報を取得
            stock_info = self._get_detailed_stock_info(code)
            if not stock_info:
                return {'error': '銘柄情報が見つかりません', 'status': 'error'}
            
            # AI分析を実行
            analysis = self._perform_ai_analysis(stock_info)
            
            return {
                'status': 'success',
                'data': {
                    'stock_info': stock_info,
                    'analysis': analysis
                }
            }
            
        except Exception as e:
            logger.error(f"AI分析エラー: {str(e)}")
            return {'error': 'AI分析に失敗しました', 'status': 'error'}
    
    def _get_detailed_stock_info(self, code):
        """銘柄の詳細情報を取得"""
        query = """
        SELECT 
            sd.code,
            sd.name,
            sd.date,
            sd.price,
            sd.change_amount,
            sd.change_percent,
            sd.volume,
            sd.volume_ratio,
            sd.market_cap,
            sd.per,
            sd.pbr,
            CASE 
                WHEN sd.eps != 0 AND sd.bps != 0 THEN (sd.eps / sd.bps * 100)
                ELSE NULL
            END AS roe,
            sd.industry,
            sd.market,
            sd.dividend_yield,
            sd.yearly_high,
            sd.yearly_low,
            sd.vwap,
            si.rsi14,
            si.ma5,
            si.ma25,
            si.ma50,
            si.ma75,
            si.price_deviation_20,
            si.volume_deviation_20
        FROM stock_database sd
        LEFT JOIN stock_indicators si ON sd.code = si.code AND sd.date = si.date
        WHERE sd.code = ?
        AND sd.date = (SELECT MAX(date) FROM stock_database)
        """
        
        result = self.stock_data_repo.db_connector.execute_query(query, (code,))
        if not result:
            return None
            
        row = result[0]
        return {
            'code': row[0],
            'name': row[1],
            'date': row[2],
            'price': row[3],
            'change_amount': row[4],
            'change_percent': row[5],
            'volume': row[6],
            'volume_ratio': row[7],
            'market_cap': row[8],
            'per': row[9],
            'pbr': row[10],
            'roe': row[11],
            'industry': row[12],
            'market': row[13],
            'dividend_yield': row[14],
            'yearly_high': row[15],
            'yearly_low': row[16],
            'vwap': row[17],
            'rsi': row[18],
            'ma5': row[19],
            'ma25': row[20],
            'ma50': row[21],
            'ma75': row[22],
            'price_deviation_20': row[23],
            'volume_deviation_20': row[24]
        }
    
    def _perform_ai_analysis(self, stock_info):
        """AI分析を実行（デモ版）"""
        # API キーがない場合はデモ分析を返す
        if not self.api_key:
            return self._get_demo_analysis(stock_info)
        
        try:
            # DeepSeek APIを呼び出す
            prompt = self._create_analysis_prompt(stock_info)
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': 'deepseek-chat',
                'messages': [
                    {'role': 'system', 'content': 'あなたは株式市場の専門アナリストです。提供された銘柄データを分析し、投資判断に役立つ洞察を提供してください。'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.7,
                'max_tokens': 1000
            }
            
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                logger.error(f"DeepSeek API エラー: {response.status_code}")
                return self._get_demo_analysis(stock_info)
                
        except Exception as e:
            logger.error(f"AI API呼び出しエラー: {str(e)}")
            return self._get_demo_analysis(stock_info)
    
    def _create_analysis_prompt(self, stock_info):
        """AI分析用のプロンプトを作成"""
        # None値を安全に処理
        def safe_format(value, format_str="{:.2f}", default="N/A"):
            if value is None:
                return default
            try:
                return format_str.format(float(value))
            except:
                return default
        
        return f"""
以下の銘柄データを分析してください：

銘柄名: {stock_info.get('name', 'N/A')} ({stock_info.get('code', 'N/A')})
現在株価: {safe_format(stock_info.get('price'), "{:.0f}円")}
前日比: {safe_format(stock_info.get('change_amount'), "{:.0f}円")} ({safe_format(stock_info.get('change_percent'), "{:.2f}%")})
出来高: {safe_format(stock_info.get('volume'), "{:,.0f}株")}
出来高率: {safe_format(stock_info.get('volume_ratio'), "{:.0f}%")}
時価総額: {safe_format(stock_info.get('market_cap'), "{:,.0f}百万円")}
PER: {safe_format(stock_info.get('per'), "{:.1f}倍")}
PBR: {safe_format(stock_info.get('pbr'), "{:.1f}倍")}
ROE: {safe_format(stock_info.get('roe'), "{:.2f}%")}
配当利回り: {safe_format(stock_info.get('dividend_yield'), "{:.2f}%")}
業種: {stock_info.get('industry', 'N/A')}
市場: {stock_info.get('market', 'N/A')}

テクニカル指標:
RSI(14日): {safe_format(stock_info.get('rsi'), "{:.2f}")}
5日移動平均: {safe_format(stock_info.get('ma5'), "{:.2f}円")}
25日移動平均: {safe_format(stock_info.get('ma25'), "{:.2f}円")}
50日移動平均: {safe_format(stock_info.get('ma50'), "{:.2f}円")}
75日移動平均: {safe_format(stock_info.get('ma75'), "{:.2f}円")}

年初来高値: {safe_format(stock_info.get('yearly_high'), "{:.0f}円")}
年初来安値: {safe_format(stock_info.get('yearly_low'), "{:.0f}円")}
VWAP: {safe_format(stock_info.get('vwap'), "{:.2f}円")}

以下の観点から分析してください：
1. 現在の株価トレンドと勢い
2. バリュエーション（割安・割高）の評価
3. テクニカル面での売買シグナル
4. リスク要因
5. 総合的な投資判断（買い・中立・売り）

分析は簡潔に、箇条書きで記載してください。
"""
    
    def _get_demo_analysis(self, stock_info):
        """デモ用の分析結果を生成"""
        # 簡単なルールベースの分析
        analysis_points = []
        
        # トレンド分析
        price = stock_info.get('price')
        ma25 = stock_info.get('ma25')
        if price and ma25 and price > ma25:
            analysis_points.append("• 株価は25日移動平均線を上回っており、上昇トレンドを示唆")
        elif price and ma25:
            analysis_points.append("• 株価は25日移動平均線を下回っており、調整局面の可能性")
        
        # RSI分析
        rsi = stock_info.get('rsi')
        if rsi and rsi > 70:
            analysis_points.append("• RSIが70を超えており、買われ過ぎの水準")
        elif rsi and rsi < 30:
            analysis_points.append("• RSIが30を下回っており、売られ過ぎの水準")
        elif rsi:
            analysis_points.append("• RSIは中立的な水準")
        
        # バリュエーション分析
        per = stock_info.get('per')
        if per and per < 15:
            analysis_points.append("• PERは業界平均を下回り、割安感あり")
        elif per and per > 30:
            analysis_points.append("• PERは高水準で、成長期待が織り込まれている")
        
        # 出来高分析
        volume_ratio = stock_info.get('volume_ratio')
        if volume_ratio and volume_ratio > 150:
            analysis_points.append("• 出来高が急増しており、注目度が高まっている")
        elif volume_ratio and volume_ratio < 50:
            analysis_points.append("• 出来高が低調で、様子見ムード")
        
        # 総合判断
        buy_signals = sum([
            bool(price and ma25 and price > ma25),
            bool(rsi and rsi < 70),
            bool(per and per < 20),
            bool(volume_ratio and volume_ratio > 100)
        ])
        
        if buy_signals >= 3:
            analysis_points.append("\n【総合判断】買い推奨 - 複数の好条件が揃っている")
        elif buy_signals >= 2:
            analysis_points.append("\n【総合判断】中立 - 一部好条件あるが、慎重な判断が必要")
        else:
            analysis_points.append("\n【総合判断】様子見 - 明確な買いシグナルなし")
        
        analysis_points.append("\n※これはデモ分析です。実際の投資判断は自己責任でお願いします。")
        
        return "\n".join(analysis_points)
    
    def analyze_screening_results(self, query, screening_results, include_chart_data=False):
        """スクリーニング結果全体のAI分析を実行"""
        try:
            # 入力検証
            if not screening_results:
                return "分析対象の銘柄がありません。"
            
            # API キーがない場合はデモ分析を返す
            if not self.api_key:
                return self._get_demo_screening_analysis(query, screening_results)
            
            # プロンプトを作成
            prompt = self._create_screening_analysis_prompt(query, screening_results, include_chart_data)
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': 'deepseek-chat',
                'messages': [
                    {'role': 'system', 'content': 'あなたは株式市場の専門アナリストです。スクリーニング結果を分析し、投資判断に役立つ洞察を提供してください。'},
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': 0.7,
                'max_tokens': 2000
            }
            
            logger.info("DeepSeek APIにリクエスト送信中...")
            response = requests.post(self.api_url, headers=headers, json=data, timeout=60)
            logger.info(f"API レスポンスステータス: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                if 'choices' in result and len(result['choices']) > 0:
                    return result['choices'][0]['message']['content']
                else:
                    logger.error(f"予期しないAPIレスポンス形式: {result}")
                    return self._get_demo_screening_analysis(query, screening_results)
            else:
                logger.error(f"DeepSeek API エラー: {response.status_code}")
                logger.error(f"エラー詳細: {response.text}")
                return self._get_demo_screening_analysis(query, screening_results)
                
        except requests.exceptions.Timeout:
            logger.error("DeepSeek API タイムアウト")
            return "AI分析がタイムアウトしました。しばらく待ってから再度お試しください。"
        except Exception as e:
            logger.error(f"AI API呼び出しエラー: {str(e)}")
            logger.error(traceback.format_exc())
            return self._get_demo_screening_analysis(query, screening_results)
    
    def _create_screening_analysis_prompt(self, query, screening_results, include_chart_data):
        """スクリーニング結果分析用のプロンプトを作成"""
        # 結果のサマリーを作成
        results_summary = f"スクリーニング結果: {len(screening_results)}銘柄\n\n"
        
        for i, stock in enumerate(screening_results[:20]):  # 最大20銘柄まで
            try:
                # 基本情報
                name = stock.get('name', 'N/A')
                code = stock.get('code', 'N/A')
                results_summary += f"{i+1}. {name} ({code})\n"
                
                # 価格情報（None/null値を適切に処理）
                price = stock.get('price')
                price_str = f"{price:.0f}円" if price is not None else "N/A"
                
                change_percent = stock.get('change_percent')
                change_str = f"{change_percent:.2f}%" if change_percent is not None else "N/A"
                
                results_summary += f"   株価: {price_str} 前日比: {change_str}\n"
                
                # 出来高とファンダメンタル指標
                volume_ratio = stock.get('volume_ratio')
                volume_ratio_str = f"{volume_ratio:.2f}" if volume_ratio is not None else "N/A"
                
                roe = stock.get('roe')
                roe_str = f"{roe:.2f}%" if roe is not None else "N/A"
                
                per = stock.get('per')
                per_str = f"{per:.2f}" if per is not None else "N/A"
                
                results_summary += f"   出来高率: {volume_ratio_str} ROE: {roe_str} PER: {per_str}\n"
                
                # テクニカル指標（オプション）
                if include_chart_data:
                    rsi = stock.get('rsi14')
                    if rsi is not None:
                        rsi_str = f"{rsi:.2f}" if isinstance(rsi, (int, float)) else "N/A"
                        results_summary += f"   RSI: {rsi_str}"
                    
                    ma5 = stock.get('ma5')
                    if ma5 is not None:
                        ma5_str = f"{ma5:.2f}円" if isinstance(ma5, (int, float)) else "N/A"
                        results_summary += f" 5日MA: {ma5_str}"
                    
                    ma25 = stock.get('ma25')
                    if ma25 is not None:
                        ma25_str = f"{ma25:.2f}円" if isinstance(ma25, (int, float)) else "N/A"
                        results_summary += f" 25日MA: {ma25_str}"
                    
                    results_summary += "\n"
                
                results_summary += "\n"
                
            except Exception as e:
                logger.error(f"銘柄データ処理エラー ({i+1}番目): {str(e)}")
                results_summary += f"   データ処理エラー\n\n"
        
        if len(screening_results) > 20:
            results_summary += f"... 他 {len(screening_results) - 20}銘柄\n"
        
        return f"""
以下のスクリーニング結果について、次の質問に答えてください：

{query}

{results_summary}

分析の際は以下の観点を考慮してください：
1. 各銘柄の財務指標とテクニカル指標
2. 業種やセクターの傾向
3. 短期的・中長期的な投資機会
4. リスク要因
5. 具体的な投資戦略の提案

回答は具体的で実用的な内容にしてください。
"""
    
    def _get_demo_screening_analysis(self, query, screening_results):
        """デモ用のスクリーニング結果分析を生成"""
        analysis = f"【デモ分析】\n\n"
        analysis += f"スクリーニング結果 {len(screening_results)}銘柄について分析します。\n\n"
        
        # 簡単な統計分析
        if screening_results:
            # None値を除外して平均を計算
            change_values = [s.get('change_percent', 0) for s in screening_results if s.get('change_percent') is not None]
            avg_change = sum(change_values) / len(change_values) if change_values else 0
            positive_count = sum(1 for s in screening_results if s.get('change_percent', 0) > 0)
            
            analysis += f"◆ 基本統計\n"
            analysis += f"- 平均前日比: {avg_change:.2f}%\n"
            analysis += f"- 上昇銘柄数: {positive_count}銘柄 ({positive_count/len(screening_results)*100:.1f}%)\n\n"
            
            # 上位銘柄の分析
            top_gainers = sorted(screening_results, key=lambda x: x.get('change_percent', 0), reverse=True)[:3]
            if top_gainers:
                analysis += f"◆ 上昇率上位銘柄\n"
                for stock in top_gainers:
                    name = stock.get('name', 'N/A')
                    code = stock.get('code', 'N/A')
                    change = stock.get('change_percent', 0)
                    analysis += f"- {name} ({code}): {change:.2f}%\n"
                analysis += "\n"
            
            # 出来高分析
            high_volume = [s for s in screening_results if s.get('volume_ratio', 0) > 150]
            if high_volume:
                analysis += f"◆ 出来高急増銘柄 ({len(high_volume)}銘柄)\n"
                for stock in high_volume[:3]:
                    name = stock.get('name', 'N/A')
                    code = stock.get('code', 'N/A')
                    volume_ratio = stock.get('volume_ratio', 0)
                    analysis += f"- {name} ({code}): 出来高率 {volume_ratio:.0f}%\n"
        
        analysis += "\n※これはデモ分析です。実際のAI分析にはAPIキーの設定が必要です。"
        
        return analysis

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
            
        # デバッグ用にパラメータをログ出力
        logger.info(f"スクリーニングパラメータ: {dict(request.args)}")
        
        # クエリパラメータを取得
        market = request.args.get('market', '')
        sector = request.args.get('sector', '')
        min_volume = request.args.get('min_volume', type=int)
        max_volume = request.args.get('max_volume', type=int)
        min_market_cap = request.args.get('min_market_cap', type=float)
        max_market_cap = request.args.get('max_market_cap', type=float)
        min_per = request.args.get('min_per', type=float)
        max_per = request.args.get('max_per', type=float)
        min_pbr = request.args.get('min_pbr', type=float)
        max_pbr = request.args.get('max_pbr', type=float)
        min_roe = request.args.get('min_roe', type=float)
        max_roe = request.args.get('max_roe', type=float)
        is_credit_issue = request.args.get('is_credit_issue')
        
        # パターンスクリーニングのパラメータ
        pattern_vwap_golden_cross = request.args.get('pattern_vwap_golden_cross', 'false').lower() == 'true'
        pattern_upper_shadow = request.args.get('pattern_upper_shadow', 'false').lower() == 'true'
        pattern_volume_golden_cross = request.args.get('pattern_volume_golden_cross', 'false').lower() == 'true'
        margin_lending_only = request.args.get('margin_lending_only', 'false').lower() == 'true'
        
        # 追加のスクリーニングパラメータ
        min_vwap = request.args.get('min_vwap', type=float)
        max_vwap = request.args.get('max_vwap', type=float)
        min_dividend_yield = request.args.get('min_dividend_yield', type=float)
        max_dividend_yield = request.args.get('max_dividend_yield', type=float)
        min_volume_ratio = request.args.get('min_volume_ratio', type=float)
        max_volume_ratio = request.args.get('max_volume_ratio', type=float)
        min_shares_issued = request.args.get('min_shares_issued', type=int)
        max_shares_issued = request.args.get('max_shares_issued', type=int)
        
        # 基本クエリ（stock_indicatorsテーブルと結合）
        query = """
        SELECT 
            sd.code, 
            sd.name, 
            sd.date AS stock_date, 
            sd.price AS price, 
            sd.change_amount,
            sd.change_percent,
            sd.volume, 
            sd.volume_ratio,
            sd.market_cap,
            sd.per, 
            sd.pbr, 
            CASE 
                WHEN sd.eps != 0 AND sd.bps != 0 THEN (sd.eps / sd.bps * 100)
                ELSE NULL
            END AS roe, 
            sd.industry AS sector, 
            sd.industry, 
            sd.market,
            sd.dividend_yield,
            sd.margin_buying, 
            sd.margin_selling,
            sd.margin_ratio,
            sd.yearly_high,
            sd.yearly_low,
            sd.yearly_low_date,
            sd.shares_issued,
            sd.vwap,
            sd.high_price,
            sd.low_price,
            sd.open_price,
            si.price_deviation_20,
            si.price_deviation_100,
            si.volume_deviation_20,
            si.volume_deviation_100,
            si.stock_lending_repayment_ratio,
            si.jsf_diff_ratio,
            si.short_ratio,
            si.margin_buying_deviation_20,
            si.volume_golden_cross,
            si.price_golden_cross,
            si.ma5,
            si.ma25,
            si.ma50,
            si.ma75,
            si.rsi14,
            si.margin_buying_volume_ratio,
            sd.jsf_loan_balance,
            sd.jsf_stock_lending_balance,
            sd.jsf_net_balance
        FROM stock_database sd
        LEFT JOIN stock_indicators si ON sd.code = si.code AND sd.date = si.date
        WHERE sd.date = (SELECT MAX(date) FROM stock_database)
        """
        
        # 条件を追加
        conditions = []
        params = []
        
        # 市場
        if market:
            conditions.append("sd.market = ?")
            params.append(market)
            
        # 業種
        if sector:
            conditions.append("sd.industry = ?")
            params.append(sector)
            
        # 出来高
        if min_volume is not None:
            conditions.append("sd.volume >= ?")
            params.append(min_volume)
        if max_volume is not None:
            conditions.append("sd.volume <= ?")
            params.append(max_volume)
            
        # 時価総額
        if min_market_cap is not None:
            conditions.append("sd.market_cap >= ?")
            params.append(min_market_cap)
        if max_market_cap is not None:
            conditions.append("sd.market_cap <= ?")
            params.append(max_market_cap)
            
        # PER
        if min_per is not None:
            conditions.append("CAST(REPLACE(REPLACE(sd.per, '倍', ''), '-', '') AS REAL) >= ?")
            params.append(min_per)
        if max_per is not None:
            conditions.append("CAST(REPLACE(REPLACE(sd.per, '倍', ''), '-', '') AS REAL) <= ?")
            params.append(max_per)
            
        # PBR
        if min_pbr is not None:
            conditions.append("CAST(REPLACE(REPLACE(sd.pbr, '倍', ''), '-', '') AS REAL) >= ?")
            params.append(min_pbr)
        if max_pbr is not None:
            conditions.append("CAST(REPLACE(REPLACE(sd.pbr, '倍', ''), '-', '') AS REAL) <= ?")
            params.append(max_pbr)
            
        # ROE
        if min_roe is not None:
            conditions.append("(CASE WHEN sd.eps != 0 AND sd.bps != 0 THEN (sd.eps / sd.bps * 100) ELSE NULL END) >= ?")
            params.append(min_roe)
        if max_roe is not None:
            conditions.append("(CASE WHEN sd.eps != 0 AND sd.bps != 0 THEN (sd.eps / sd.bps * 100) ELSE NULL END) <= ?")
            params.append(max_roe)
            
        # 信用銘柄
        if is_credit_issue is not None:
            conditions.append("(CASE WHEN sd.margin_buying IS NOT NULL OR sd.margin_selling IS NOT NULL THEN 1 ELSE 0 END) = ?")
            params.append(int(is_credit_issue))
            
        # VWAP
        if min_vwap is not None:
            conditions.append("sd.vwap >= ?")
            params.append(min_vwap)
        if max_vwap is not None:
            conditions.append("sd.vwap <= ?")
            params.append(max_vwap)
            
        # 配当利回り
        if min_dividend_yield is not None:
            conditions.append("sd.dividend_yield >= ?")
            params.append(min_dividend_yield)
        if max_dividend_yield is not None:
            conditions.append("sd.dividend_yield <= ?")
            params.append(max_dividend_yield)
            
        # 出来高率
        if min_volume_ratio is not None:
            conditions.append("sd.volume_ratio >= ?")
            params.append(min_volume_ratio)
        if max_volume_ratio is not None:
            conditions.append("sd.volume_ratio <= ?")
            params.append(max_volume_ratio)
            
        # 発行済株式数
        if min_shares_issued is not None:
            conditions.append("sd.shares_issued >= ?")
            params.append(min_shares_issued)
        if max_shares_issued is not None:
            conditions.append("sd.shares_issued <= ?")
            params.append(max_shares_issued)
            
        # VWAPゴールデンクロスパターンの条件
        if pattern_vwap_golden_cross:
            conditions.append("sd.vwap IS NOT NULL AND sd.price > sd.vwap")
            
        # 上髭パターンの条件
        if pattern_upper_shadow:
            conditions.append("(sd.high_price - CASE WHEN sd.open_price > sd.price THEN sd.open_price ELSE sd.price END) > ABS(sd.price - sd.open_price) * 2")
            conditions.append("sd.price < sd.open_price")  # 陰線
            
        # 出来高ゴールデンクロスパターンの条件
        if pattern_volume_golden_cross:
            conditions.append("si.volume_golden_cross = 1")
            
        # 貸借銘柄のみ
        if margin_lending_only:
            conditions.append("(sd.margin_buying IS NOT NULL OR sd.margin_selling IS NOT NULL)")
            
        if conditions:
            query += " AND " + " AND ".join(conditions)
            
        logger.info(f"実行するクエリ: {query[:200]}...")  # 最初の200文字だけログ出力
        results = stock_data_repository.db_connector.execute_query(query, params)
        logger.info(f"クエリ結果件数: {len(results)}")
        
        # 結果を整形
        stocks = []
        for row in results:
            stock_data = {
                'code': row[0],
                'name': row[1],
                'stock_date': row[2],
                'price': float(row[3]) if row[3] else None,
                'change_amount': float(row[4]) if row[4] else 0,
                'change_percent': float(row[5]) if row[5] else 0,
                'volume': int(row[6]) if row[6] else 0,
                'volume_ratio': float(row[7]) if row[7] else None,
                'market_cap': float(row[8]) if row[8] else None,
                'per': float(row[9]) if row[9] and str(row[9]).replace('.', '').replace('-', '').isdigit() else None,
                'pbr': float(row[10]) if row[10] and str(row[10]).replace('.', '').replace('-', '').isdigit() else None,
                'roe': float(row[11]) if row[11] else None,
                'sector': row[12],
                'industry': row[13],
                'market': row[14],
                'dividend_yield': float(row[15]) if row[15] else None,
                'margin_buying': int(row[16]) if row[16] else None,
                'margin_selling': int(row[17]) if row[17] else None,
                'margin_ratio': float(row[18]) if row[18] else None,
                'yearly_high': float(row[19]) if row[19] else None,
                'yearly_low': float(row[20]) if row[20] else None,
                'yearly_low_date': row[21],
                'shares_issued': int(row[22]) if row[22] else None,
                'vwap': float(row[23]) if row[23] else None,
                'high': float(row[24]) if row[24] else None,
                'low': float(row[25]) if row[25] else None,
                'open': float(row[26]) if row[26] else None,
                'price_deviation_20': float(row[27]) if row[27] else None,
                'price_deviation_100': float(row[28]) if row[28] else None,
                'volume_deviation_20': float(row[29]) if row[29] else None,
                'volume_deviation_100': float(row[30]) if row[30] else None,
                'stock_lending_repayment_ratio': float(row[31]) if row[31] else None,
                'jsf_diff_ratio': float(row[32]) if row[32] else None,
                'short_ratio': float(row[33]) if row[33] else None,
                'margin_buying_deviation_20': float(row[34]) if row[34] else None,
                'volume_golden_cross': int(row[35]) if row[35] else 0,
                'price_golden_cross': int(row[36]) if row[36] else 0,
                'ma5': float(row[37]) if row[37] else None,
                'ma25': float(row[38]) if row[38] else None,
                'ma50': float(row[39]) if row[39] else None,
                'ma75': float(row[40]) if row[40] else None,
                'rsi14': float(row[41]) if row[41] else None,
                'margin_buying_volume_ratio': float(row[42]) if row[42] else None,
                'jsf_loan_balance': int(row[43]) if row[43] else None,
                'jsf_stock_lending_balance': int(row[44]) if row[44] else None,
                'jsf_net_balance': int(row[45]) if row[45] else None
            }
            stocks.append(stock_data)
            
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
        logger.info(f"推奨起動コマンド: gunicorn -w 4 -b {host}:{port} app_ubuntu_version_fixed_v7_chart_final_ai_analysis:app")
        logger.info(f"または環境変数を設定:")
        logger.info(f"  export STOCK_APP_BASE_PATH=/path/to/app")
        logger.info(f"  export STOCK_DB_PATH=/path/to/database.sqlite3")
        logger.info(f"  export FLASK_ENV=production")
        logger.info(f"  export SECRET_KEY=your-secret-key")
        logger.info(f"  export ALLOWED_ORIGINS=https://yourdomain.com")
        logger.info(f"  export DEEPSEEK_API_KEY=your-api-key  # AI分析を有効にする場合")
        #app.run(host=host, port=port, debug=False)