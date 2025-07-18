"""
拡張APIバージョン6（日付フィルター + 信用買残高÷出来高 + 貸借銘柄フィルター）

主な機能：
1. チャートパターンのスクリーニング
2. 日付フィルター機能
3. 信用買残高÷出来高フィルター（margin_buying_volume_ratio使用）
4. 貸借銘柄フィルター機能（新規追加）
5. モジュール化された構造

変更点:
- 貸借銘柄フィルター機能を追加
- stock_indicatorsテーブルのmargin_categoryカラムを参照
"""

from flask import request, jsonify, render_template
import traceback
from typing import Dict, List, Any

from .v6_modules import (
    BaseAPIHandler,
    DebugAPIHandler,
    DataFormatter
)
from .v6_modules.filter_processor import FilterProcessor
from .v6_modules.query_builder_margin_buying_volume_ratio_v4 import QueryBuilder


class EnhancedAPIFixedV6WithMarginLending(BaseAPIHandler):
    """修正版拡張APIルートとハンドラを管理するクラス（貸借銘柄フィルター対応）"""
    
    def __init__(self, app, service, repository, chart_service, logger):
        """APIルートの初期化
        
        Args:
            app: Flaskアプリケーションインスタンス
            service: 株価サービスインスタンス
            repository: 株価リポジトリインスタンス
            chart_service: チャートサービスインスタンス
            logger: ロガーインスタンス
        """
        super().__init__(app, service, repository, chart_service, logger)
        
        # モジュールの初期化
        self.filter_processor = FilterProcessor(logger)
        self.query_builder = QueryBuilder(logger)  # 修正版のQueryBuilderを使用
        self.data_formatter = DataFormatter(logger)
        
        # デバッグハンドラの初期化と登録
        self.debug_handler = DebugAPIHandler(app, service, repository, chart_service, logger)
        self.debug_handler.register_routes()
        
        # ルート登録
        self._register_routes()
        self.logger.info("修正版拡張APIルートを登録しました（貸借銘柄フィルター対応版）")
    
    def _register_routes(self):
        """APIルートを登録する"""
        # 拡張版メインページ
        self.app.route('/enhanced')(self.enhanced_index)
        
        # 拡張版APIエンドポイント
        self.app.route('/api/enhanced-screening', methods=['GET'])(self.enhanced_screen_stocks)
    
    def enhanced_index(self):
        """拡張版メインページを表示
        
        Returns:
            str: レンダリングされたHTMLテンプレート
        """
        try:
            return render_template('index_with_enhanced_screening_vgc_fixed_with_vwap_margin_lending.html')
        except Exception as e:
            self.logger.error(f"拡張版テンプレートレンダリングエラー: {e}")
            return f"Error: {str(e)}"
    
    def enhanced_screen_stocks(self):
        """拡張版スクリーニング条件に基づいて銘柄をフィルタリングする
        
        Returns:
            Tuple[Dict, int]: JSON応答とHTTPステータスコード
        """
        try:
            # すべてのフィルター条件を取得
            filters = self.filter_processor.collect_all_filters(request.args)
            
            self.logger.info(f"拡張版スクリーニング条件: {filters}")
            
            # スクリーニングを実行
            results = self._enhanced_screen_stocks_fixed(filters)
            
            return jsonify({
                'status': 'success',
                'data': results,
                'filters': filters,
                'count': len(results)
            }), 200
        except Exception as e:
            self.logger.error(f"拡張版スクリーニングエラー: {e}")
            traceback.print_exc()
            return jsonify({
                'status': 'error',
                'message': str(e)
            }), 500
    
    def _enhanced_screen_stocks_fixed(self, filters: Dict) -> List[Dict]:
        """修正版の拡張スクリーニングを実行する
        
        Args:
            filters: フィルター条件
            
        Returns:
            List[Dict]: スクリーニング結果
        """
        self.logger.info("修正版拡張スクリーニングを開始（貸借銘柄フィルター対応）")
        
        # 日付フィルターの処理
        target_date = filters.get('target_date')
        if target_date:
            self.logger.info(f"指定日付でのスクリーニング: {target_date}")
        else:
            self.logger.info("最新日付でのスクリーニング")
        
        # データベース接続を取得
        conn = self.get_db_connection()
        if conn is None:
            return []
        
        try:
            # 信用関連指標のカラムをチェック
            credit_columns = self._check_credit_indicator_columns(conn)
            self.logger.info(f"信用関連指標カラム確認結果: {credit_columns}")
            
            # フィルタータイプをチェック
            filter_types = self.filter_processor.check_filter_types(filters)
            
            # クエリを構築
            query, params = self.query_builder.build_screening_query(
                filters, filter_types, credit_columns
            )
            
            # デバッグ: クエリの最初の500文字を出力
            self.logger.debug(f"生成されたクエリ（最初の500文字）: {query[:500]}")
            self.logger.debug(f"パラメータ数: {len(params)}")
            
            # 一時的に完全なクエリを出力（デバッグ用）
            print("\n=== 生成されたSQL ===\n")
            print(query)
            print("\n=== パラメータ ===\n")
            print(params)
            print("\n==================\n")
            
            # クエリを実行
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            # 結果をフォーマット
            results = self.data_formatter.format_screening_results(rows)
            
            self.logger.info(f"拡張版スクリーニング結果: {len(results)}件")
            return results
            
        except Exception as e:
            self.logger.error(f"クエリ実行エラー: {e}")
            traceback.print_exc()
            return []
        finally:
            conn.close()
    
    def _check_credit_indicator_columns(self, conn) -> Dict[str, bool]:
        """信用関連指標のカラムが存在するかチェックする
        
        Args:
            conn: データベース接続
            
        Returns:
            Dict: カラムの存在状況
        """
        try:
            cursor = conn.execute("PRAGMA table_info(stock_indicators)")
            columns = {col[1] for col in cursor.fetchall()}
            
            return {
                'stock_lending_repayment_ratio': 'stock_lending_repayment_ratio' in columns,
                'jsf_diff_ratio': 'jsf_diff_ratio' in columns,
                'short_ratio': 'short_ratio' in columns,
                'margin_buying_deviation_20': 'margin_buying_deviation_20' in columns,
                'volume_golden_cross': 'volume_golden_cross' in columns,
                'price_golden_cross': 'price_golden_cross' in columns,
                'vwap_golden_cross': 'vwap_golden_cross' in columns,
                'margin_buying_volume_ratio': 'margin_buying_volume_ratio' in columns,
                'margin_category': 'margin_category' in columns  # 貸借銘柄フィルター用
            }
        except Exception as e:
            self.logger.error(f"カラムチェックエラー: {e}")
            return {}
