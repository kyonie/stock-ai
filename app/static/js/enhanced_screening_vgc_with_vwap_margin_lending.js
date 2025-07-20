// 拡張版株価スクリーニング用JavaScriptファイル（VWAPゴールデンクロス + 貸借銘柄フィルター対応版）
$(document).ready(function() {
    // グローバル変数でスクリーニング結果を保持
    let currentResults = [];
    let currentSortColumn = null;
    let currentSortDirection = 'asc';
    let availableDates = [];
    let selectedDate = null;
    let latestDateValue = null;
    
    // ページ読み込み時に利用可能な日付を取得
    loadAvailableDates();
    
    // 日付オプションの変更イベント
    $('input[name="dateOption"]').change(function() {
        if ($(this).val() === 'latest') {
            $('#dateSelect').prop('disabled', true);
            $('#dateSelect').val('');
            selectedDate = null;
            updateSelectedDateDisplay();
            updateDataCount();
        } else {
            $('#dateSelect').prop('disabled', false);
        }
    });
    
    // 日付選択の変更イベント
    $('#dateSelect').change(function() {
        selectedDate = $(this).val();
        updateSelectedDateDisplay();
        if (selectedDate) {
            updateDataCount(selectedDate);
        }
    });
    
    // スクリーニング開始ボタンのイベントハンドラ
    $('#startScreening').click(function() {
        startScreening();
    });
    
    // リセットボタンのイベントハンドラ
    $('#resetFilters').click(function() {
        resetAllFilters();
    });
    
    // キャッシュクリアボタンのイベントハンドラ
    $('#clearCache').click(function() {
        clearCache();
    });
    
    // フィルターが変更されたら適用されていることを視覚的に示す
    $('input, select').on('change', function() {
        updateFilterVisuals();
    });
    
    // ソート可能な列のクリックイベントを動的に設定
    $(document).on('click', '.sortable', function() {
        const column = $(this).data('sort');
        sortResults(column);
    });
    
    // 利用可能な日付を取得して表示する関数
    function loadAvailableDates() {
        $.ajax({
            url: '/api/available-dates',
            method: 'GET',
            success: function(response) {
                availableDates = response.dates || [];
                const $dateSelect = $('#dateSelect');
                $dateSelect.empty();
                $dateSelect.append('<option value="">日付を選択...</option>');
                
                availableDates.forEach(function(date) {
                    // YYYYMMDD形式をYYYY-MM-DD形式に変換
                    let dateStr = date;
                    if (date && date.length === 8 && !date.includes('-')) {
                        dateStr = date.substring(0, 4) + '-' + date.substring(4, 6) + '-' + date.substring(6, 8);
                    }
                    
                    const dateObj = new Date(dateStr);
                    let formattedDate;
                    
                    // 日付が有効かチェック
                    if (!isNaN(dateObj.getTime())) {
                        formattedDate = dateObj.toLocaleDateString('ja-JP', {
                            year: 'numeric',
                            month: 'long',
                            day: 'numeric'
                        });
                    } else {
                        // フォールバック: 元の文字列を表示
                        formattedDate = date;
                    }
                    
                    $dateSelect.append(`<option value="${date}">${formattedDate}</option>`);
                });
                
                // 最新日付を取得して表示
                updateLatestDataDate();
            },
            error: function() {
                console.error('利用可能日付の取得エラー');
            }
        });
    }
    
    // 最新データ日付を取得して表示する関数
    function updateLatestDataDate() {
        $.ajax({
            url: '/api/latest-data-date',
            method: 'GET',
            success: function(response) {
                if (response.latest_date) {
                    latestDateValue = response.latest_date;
                    
                    // YYYYMMDD形式をYYYY-MM-DD形式に変換
                    let dateStr = response.latest_date;
                    if (dateStr && dateStr.length === 8 && !dateStr.includes('-')) {
                        dateStr = dateStr.substring(0, 4) + '-' + dateStr.substring(4, 6) + '-' + dateStr.substring(6, 8);
                    }
                    
                    const latestDate = new Date(dateStr);
                    let formattedDate;
                    
                    // 日付が有効かチェック
                    if (!isNaN(latestDate.getTime())) {
                        formattedDate = latestDate.toLocaleDateString('ja-JP', {
                            year: 'numeric',
                            month: 'long',
                            day: 'numeric'
                        });
                    } else {
                        formattedDate = response.latest_date;
                    }
                    
                    $('#latestDateBadge').text(formattedDate);
                    
                    // 初回はデータ件数も更新
                    if ($('input[name="dateOption"]:checked').val() === 'latest') {
                        updateDataCount();
                    }
                }
            },
            error: function() {
                $('#latestDateBadge').text('エラー');
            }
        });
    }
    
    // 選択中の日付表示を更新
    function updateSelectedDateDisplay() {
        const isLatest = $('input[name="dateOption"]:checked').val() === 'latest';
        if (isLatest) {
            $('#selectedDateDisplay').text('最新データ');
        } else if (selectedDate) {
            // YYYYMMDD形式をYYYY-MM-DD形式に変換
            let dateStr = selectedDate;
            if (selectedDate && selectedDate.length === 8 && !selectedDate.includes('-')) {
                dateStr = selectedDate.substring(0, 4) + '-' + selectedDate.substring(4, 6) + '-' + selectedDate.substring(6, 8);
            }
            
            const dateObj = new Date(dateStr);
            let formattedDate;
            
            // 日付が有効かチェック
            if (!isNaN(dateObj.getTime())) {
                formattedDate = dateObj.toLocaleDateString('ja-JP', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                });
            } else {
                formattedDate = selectedDate;
            }
            
            $('#selectedDateDisplay').text(formattedDate);
        } else {
            $('#selectedDateDisplay').text('日付未選択');
        }
    }
    
    // データ件数を更新
    function updateDataCount(targetDate) {
        const url = targetDate ? 
            `/api/data-count-by-date?date=${targetDate}` : 
            '/api/data-count-by-date';
            
        $.ajax({
            url: url,
            method: 'GET',
            success: function(response) {
                const stockCount = response.stock_count || 0;
                const indicatorCount = response.indicator_count || 0;
                $('#dataCountInfo').html(
                    `株価データ: <strong>${stockCount.toLocaleString()}</strong>件 / ` +
                    `指標データ: <strong>${indicatorCount.toLocaleString()}</strong>件`
                );
            },
            error: function() {
                $('#dataCountInfo').text('取得エラー');
            }
        });
    }
    
    // キャッシュをクリアする関数
    function clearCache() {
        // 確認ダイアログを表示
        if (!confirm('キャッシュをクリアしますか？\n前日のデータがキャッシュされている場合、最新データが反映されます。')) {
            return;
        }
        
        // キャッシュクリアボタンを無効化
        $('#clearCache').prop('disabled', true);
        $('#clearCache').html('<i class="fas fa-spinner fa-spin"></i> クリア中...');
        
        $.ajax({
            url: '/api/clear-cache',
            method: 'POST',
            success: function(response) {
                if (response.success) {
                    // 成功メッセージを表示
                    alert('キャッシュをクリアしました。最新データが反映されます。');
                    
                    // 日付情報を再読み込み
                    loadAvailableDates();
                    
                    // ページをリロード
                    setTimeout(function() {
                        window.location.reload();
                    }, 1000);
                } else {
                    alert('キャッシュクリアに失敗しました: ' + response.message);
                }
            },
            error: function() {
                alert('キャッシュクリアエラーが発生しました。');
            },
            complete: function() {
                // ボタンを元に戻す
                $('#clearCache').prop('disabled', false);
                $('#clearCache').html('<i class="fas fa-sync-alt"></i> キャッシュをクリア');
            }
        });
    }
    
    // スクリーニング処理を開始する関数
    function startScreening() {
        const filters = collectFilters();
        
        // 日付フィルターを追加
        const isLatest = $('input[name="dateOption"]:checked').val() === 'latest';
        if (!isLatest && selectedDate) {
            filters.target_date = selectedDate;
        }
        
        // ローディング表示
        $('#loadingMessage').removeClass('d-none');
        $('#errorMessage').addClass('d-none');
        $('#resultTable').addClass('d-none');
        $('#resultStats').addClass('d-none');
        $('#activeFilters').addClass('d-none');
        $('#resultContainer').removeClass('d-none');
        
        // スクリーニングAPI呼び出し
        $.ajax({
            url: '/api/enhanced-screening',
            method: 'GET',
            data: filters,
            beforeSend: function() {
                // ローディング表示
                $('#startScreening').html('<i class="fas fa-spinner fa-spin"></i> 処理中...');
                $('#startScreening').prop('disabled', true);
            },
            success: function(response) {
                // response.dataにデータが格納されている
                currentResults = response.data || [];
                displayScreeningResults(currentResults, filters);
                
                // 結果の日付を表示
                if (currentResults.length > 0 && currentResults[0].stock_date) {
                    // YYYYMMDD形式をYYYY-MM-DD形式に変換
                    let dateStr = currentResults[0].stock_date;
                    if (dateStr && dateStr.length === 8 && !dateStr.includes('-')) {
                        dateStr = dateStr.substring(0, 4) + '-' + dateStr.substring(4, 6) + '-' + dateStr.substring(6, 8);
                    }
                    
                    const resultDate = new Date(dateStr);
                    let formattedDate;
                    
                    // 日付が有効かチェック
                    if (!isNaN(resultDate.getTime())) {
                        formattedDate = resultDate.toLocaleDateString('ja-JP', {
                            year: 'numeric',
                            month: 'long',
                            day: 'numeric'
                        });
                    } else {
                        formattedDate = currentResults[0].stock_date;
                    }
                    
                    $('#resultDate').text(formattedDate);
                } else {
                    $('#resultDate').text('-');
                }
            },
            error: function(xhr, status, error) {
                $('#errorMessage').text('サーバーエラーが発生しました: ' + error);
                $('#errorMessage').removeClass('d-none');
                console.error('API Error:', xhr.responseText);
            },
            complete: function() {
                // ローディング表示を元に戻す
                $('#loadingMessage').addClass('d-none');
                $('#startScreening').html('<i class="fas fa-filter"></i> スクリーニング開始');
                $('#startScreening').prop('disabled', false);
            }
        });
    }
    
    // スクリーニング条件を収集する関数
    function collectFilters() {
        const filters = {};
        
        // 基本条件
        if ($('#marketSelect').val()) {
            filters.market = $('#marketSelect').val();
        }
        
        if ($('#sectorSelect').val()) {
            filters.sector = $('#sectorSelect').val();
        }
        
        if ($('#minPrice').val()) {
            filters.min_price = $('#minPrice').val();
        }
        
        if ($('#maxPrice').val()) {
            filters.max_price = $('#maxPrice').val();
        }
        
        // 前日比変化率（新規追加）
        if ($('#minChangePercent').val()) {
            filters.min_change_percent = $('#minChangePercent').val();
        }
        
        if ($('#maxChangePercent').val()) {
            filters.max_change_percent = $('#maxChangePercent').val();
        }
        
        // 財務指標
        if ($('#minRoe').val()) {
            filters.min_roe = $('#minRoe').val();
        }
        
        if ($('#maxRoe').val()) {
            filters.max_roe = $('#maxRoe').val();
        }
        
        if ($('#minVwap').val()) {
            filters.min_vwap = $('#minVwap').val();
        }
        
        if ($('#maxVwap').val()) {
            filters.max_vwap = $('#maxVwap').val();
        }
        
        if ($('#minPer').val()) {
            filters.min_per = $('#minPer').val();
        }
        
        if ($('#maxPer').val()) {
            filters.max_per = $('#maxPer').val();
        }
        
        if ($('#minPbr').val()) {
            filters.min_pbr = $('#minPbr').val();
        }
        
        if ($('#maxPbr').val()) {
            filters.max_pbr = $('#maxPbr').val();
        }
        
        if ($('#minDividendYield').val()) {
            filters.min_dividend_yield = $('#minDividendYield').val();
        }
        
        if ($('#maxDividendYield').val()) {
            filters.max_dividend_yield = $('#maxDividendYield').val();
        }
        
        // 発行済株式数（百万株を株数に変換）
        if ($('#minSharesIssued').val()) {
            filters.min_shares_issued = parseFloat($('#minSharesIssued').val()) * 1000000;
        }
        
        if ($('#maxSharesIssued').val()) {
            filters.max_shares_issued = parseFloat($('#maxSharesIssued').val()) * 1000000;
        }
        
        // 時価総額（億円を百万円に変換）
        if ($('#minMarketCap').val()) {
            filters.min_market_cap = parseFloat($('#minMarketCap').val()) * 100;
        }
        
        if ($('#maxMarketCap').val()) {
            filters.max_market_cap = parseFloat($('#maxMarketCap').val()) * 100;
        }
        
        // 出来高・価格指標
        if ($('#minVolumeRatio').val()) {
            filters.min_volume_ratio = $('#minVolumeRatio').val();
        }
        
        if ($('#maxVolumeRatio').val()) {
            filters.max_volume_ratio = $('#maxVolumeRatio').val();
        }
        
        if ($('#minVolumeDeviation').val()) {
            filters.min_volume_deviation_20 = $('#minVolumeDeviation').val();
        }
        
        if ($('#maxVolumeDeviation').val()) {
            filters.max_volume_deviation_20 = $('#maxVolumeDeviation').val();
        }
        
        if ($('#minVolumeDeviation100').val()) {
            filters.min_volume_deviation_100 = $('#minVolumeDeviation100').val();
        }
        
        if ($('#maxVolumeDeviation100').val()) {
            filters.max_volume_deviation_100 = $('#maxVolumeDeviation100').val();
        }
        
        if ($('#minPriceDeviation20').val()) {
            filters.min_price_deviation_20 = $('#minPriceDeviation20').val();
        }
        
        if ($('#maxPriceDeviation20').val()) {
            filters.max_price_deviation_20 = $('#maxPriceDeviation20').val();
        }
        
        if ($('#minPriceDeviation100').val()) {
            filters.min_price_deviation_100 = $('#minPriceDeviation100').val();
        }
        
        if ($('#maxPriceDeviation100').val()) {
            filters.max_price_deviation_100 = $('#maxPriceDeviation100').val();
        }
        
        // RSI指標（新規追加）
        if ($('#minRsi').val()) {
            filters.min_rsi = $('#minRsi').val();
        }
        
        if ($('#maxRsi').val()) {
            filters.max_rsi = $('#maxRsi').val();
        }
        
        // 年初来高値・安値比率（新規追加）
        if ($('#minYearlyHighRatio').val()) {
            filters.min_yearly_high_ratio = $('#minYearlyHighRatio').val();
        }
        
        if ($('#maxYearlyHighRatio').val()) {
            filters.max_yearly_high_ratio = $('#maxYearlyHighRatio').val();
        }
        
        if ($('#minYearlyLowRatio').val()) {
            filters.min_yearly_low_ratio = $('#minYearlyLowRatio').val();
        }
        
        if ($('#maxYearlyLowRatio').val()) {
            filters.max_yearly_low_ratio = $('#maxYearlyLowRatio').val();
        }
        
        // 信用指標
        if ($('#minStockLendingRepaymentRatio').val()) {
            filters.min_stock_lending_repayment_ratio = $('#minStockLendingRepaymentRatio').val();
        }
        
        if ($('#maxStockLendingRepaymentRatio').val()) {
            filters.max_stock_lending_repayment_ratio = $('#maxStockLendingRepaymentRatio').val();
        }
        
        if ($('#minJsfDiffRatio').val()) {
            filters.min_jsf_diff_ratio = $('#minJsfDiffRatio').val();
        }
        
        if ($('#maxJsfDiffRatio').val()) {
            filters.max_jsf_diff_ratio = $('#maxJsfDiffRatio').val();
        }
        
        if ($('#minShortRatio').val()) {
            filters.min_short_ratio = $('#minShortRatio').val();
        }
        
        if ($('#maxShortRatio').val()) {
            filters.max_short_ratio = $('#maxShortRatio').val();
        }
        
        if ($('#minMarginBuyingDeviation20').val()) {
            filters.min_margin_buying_deviation_20 = $('#minMarginBuyingDeviation20').val();
        }
        
        if ($('#maxMarginBuyingDeviation20').val()) {
            filters.max_margin_buying_deviation_20 = $('#maxMarginBuyingDeviation20').val();
        }
        
        // 信用買残高÷出来高(v3)
        if ($('#minMarginBuyingVolumeRatio').val()) {
            filters.min_margin_buying_volume_ratio = $('#minMarginBuyingVolumeRatio').val();
        }
        
        if ($('#maxMarginBuyingVolumeRatio').val()) {
            filters.max_margin_buying_volume_ratio = $('#maxMarginBuyingVolumeRatio').val();
        }
        
        // 貸借銘柄フィルター（新規追加）
        if ($('#marginLendingOnly').is(':checked')) {
            filters.margin_lending_only = true;
        }
        
        // 日証金関連フィルター（新規追加）
        if ($('#minJsfLoanBalance').val()) {
            filters.min_jsf_loan_balance = parseFloat($('#minJsfLoanBalance').val()) * 1000000; // 百万株を株数に変換
        }
        
        if ($('#maxJsfLoanBalance').val()) {
            filters.max_jsf_loan_balance = parseFloat($('#maxJsfLoanBalance').val()) * 1000000;
        }
        
        if ($('#minJsfStockLendingBalance').val()) {
            filters.min_jsf_stock_lending_balance = parseFloat($('#minJsfStockLendingBalance').val()) * 1000000;
        }
        
        if ($('#maxJsfStockLendingBalance').val()) {
            filters.max_jsf_stock_lending_balance = parseFloat($('#maxJsfStockLendingBalance').val()) * 1000000;
        }
        
        if ($('#minJsfNetBalance').val()) {
            filters.min_jsf_net_balance = parseFloat($('#minJsfNetBalance').val()) * 1000000;
        }
        
        if ($('#maxJsfNetBalance').val()) {
            filters.max_jsf_net_balance = parseFloat($('#maxJsfNetBalance').val()) * 1000000;
        }
        
        // 信用倍率（新規追加）
        if ($('#minMarginRatio').val()) {
            filters.min_margin_ratio = $('#minMarginRatio').val();
        }
        
        if ($('#maxMarginRatio').val()) {
            filters.max_margin_ratio = $('#maxMarginRatio').val();
        }
        
        // チャートパターン
        if ($('#patternUpperShadow').is(':checked')) {
            filters.pattern_upper_shadow = true;
        }
        
        if ($('#patternDoji').is(':checked')) {
            filters.pattern_doji = true;
        }
        
        if ($('#patternGoldenCross').is(':checked')) {
            filters.pattern_golden_cross = true;
        }
        
        if ($('#patternDoubledPrice').is(':checked')) {
            filters.pattern_doubled_price = true;
        }
        
        // Volume Golden Cross を追加
        if ($('#patternVolumeGoldenCross').is(':checked')) {
            filters.pattern_volume_golden_cross = true;
        }
        
        // VWAP Golden Cross を追加
        if ($('#patternVwapGoldenCross').is(':checked')) {
            filters.pattern_vwap_golden_cross = true;
        }
        
        // 移動平均線ゴールデンクロス（新規追加）
        if ($('#patternMaGoldenCross').is(':checked')) {
            filters.pattern_ma_golden_cross = true;
        }
        
        // 移動平均線パターン
        if ($('#patternPriceMa25Ma50Ma75').is(':checked')) {
            filters.pattern_price_ma25_ma50_ma75 = true;
        }
        
        if ($('#patternMa50Ma25Ma75').is(':checked')) {
            filters.pattern_ma50_ma25_ma75 = true;
        }
        
        if ($('#patternMa25PriceMa75').is(':checked')) {
            filters.pattern_ma25_price_ma75 = true;
        }
        
        if ($('#patternMa50PriceMa75').is(':checked')) {
            filters.pattern_ma50_price_ma75 = true;
        }
        
        return filters;
    }
    
    // ソート関数
    function sortResults(column) {
        // ソート方向を決定
        if (currentSortColumn === column) {
            currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            currentSortColumn = column;
            currentSortDirection = 'desc'; // 新しい列は降順から開始
        }
        
        // ソート実行
        currentResults.sort((a, b) => {
            let aVal = a[column];
            let bVal = b[column];
            
            // null/undefinedの処理
            if (aVal === null || aVal === undefined) aVal = -999999;
            if (bVal === null || bVal === undefined) bVal = -999999;
            
            // 数値として比較
            aVal = parseFloat(aVal);
            bVal = parseFloat(bVal);
            
            if (currentSortDirection === 'asc') {
                return aVal - bVal;
            } else {
                return bVal - aVal;
            }
        });
        
        // テーブルを再描画
        renderResultTable(currentResults);
        
        // ソート状態の表示を更新
        updateSortIndicators(column);
    }
    
    // ソートインジケーターを更新
    function updateSortIndicators(activeColumn) {
        $('.sortable').removeClass('sort-asc sort-desc');
        if (activeColumn) {
            const $column = $(`.sortable[data-sort="${activeColumn}"]`);
            $column.addClass(currentSortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
        }
    }
    
    // スクリーニング結果を表示する関数
    function displayScreeningResults(stocks, appliedFilters) {
        // 結果件数を表示
        $('#resultCount').text(stocks.length);
        $('#resultStats').removeClass('d-none');
        
        // 該当する銘柄がない場合
        if (!stocks || stocks.length === 0) {
            const tbody = $('#resultTableBody');
            tbody.empty();
            tbody.append(`
                <tr>
                    <td colspan="17" class="text-center">条件に一致する銘柄はありません</td>
                </tr>
            `);
            $('#resultTable').removeClass('d-none');
            // AI分析ボタンも非表示
            $('#aiAnalysisSection').addClass('d-none');
        } else {
            // 結果を表示
            renderResultTable(stocks);
            $('#resultTable').removeClass('d-none');
            // AI分析ボタンを表示
            $('#aiAnalysisSection').removeClass('d-none');
            
            // スクリーニング結果をローカルストレージに保存（AI分析用）
            saveScreeningResultsForAI(stocks);
        }
        
        // 適用されたフィルター条件を表示
        displayAppliedFilters(appliedFilters);
    }
    
    // 結果テーブルを描画する関数
    function renderResultTable(stocks) {
        const tbody = $('#resultTableBody');
        tbody.empty();
        
        stocks.forEach(stock => {
            // 各値のフォーマット
            const formatValue = (value, decimals = 2, suffix = '') => {
                if (value === null || value === undefined || value === '') return '-';
                const num = parseFloat(value);
                if (isNaN(num)) return '-';
                return num.toFixed(decimals) + suffix;
            };
            
            const formatPrice = (value) => {
                if (value === null || value === undefined) return '-';
                return value.toLocaleString();
            };
            
            const changeClass = stock.change_percent >= 0 ? 'text-success' : 'text-danger';
            const changePrefix = stock.change_percent >= 0 ? '+' : '';
            
            const row = $(`
                <tr>
                    <td>${stock.code}</td>
                    <td>${stock.name}</td>
                    <td>${stock.market || '-'}</td>
                    <td>${stock.sector || '-'}</td>
                    <td class="text-end">${formatPrice(stock.price)}</td>
                    <td class="text-end ${changeClass}">
                        ${changePrefix}${formatValue(stock.change_percent, 2, '%')}
                    </td>
                    <td class="text-end">${formatValue(stock.roe, 2, '%')}</td>
                    <td class="text-end">${formatValue(stock.per)}</td>
                    <td class="text-end">${formatValue(stock.pbr)}</td>
                    <td class="text-end">${formatValue(stock.dividend_yield, 2, '%')}</td>
                    <td class="text-end">${formatValue(stock.volume_ratio)}</td>
                    <td class="text-end">${formatValue(stock.volume_deviation_20)}</td>
                    <td class="text-end">${formatValue(stock.stock_lending_repayment_ratio)}</td>
                    <td class="text-end">${formatValue(stock.jsf_diff_ratio)}</td>
                    <td class="text-end">${formatValue(stock.short_ratio, 2, '%')}</td>
                    <td class="text-end">${stock.market_cap ? (stock.market_cap / 100).toFixed(2) + '億円' : '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary view-chart" data-code="${stock.code}">
                            <i class="fas fa-chart-line"></i> チャート
                        </button>
                    </td>
                </tr>
            `);
            
            tbody.append(row);
        });
        
        // チャート表示ボタンのイベントハンドラを設定
        $('.view-chart').click(function() {
            const code = $(this).data('code');
            window.open(`/chart/${code}`, '_blank');
        });
    }
    
    // 適用されたフィルターを表示する関数
    function displayAppliedFilters(filters) {
        const filterTags = $('#filterTags');
        filterTags.empty();
        
        const filterLabels = {
            // 日付フィルター
            target_date: 'データ日付',
            // 基本条件
            market: '市場',
            sector: '業種',
            min_price: '株価下限',
            max_price: '株価上限',
            // 財務指標
            min_roe: 'ROE下限',
            max_roe: 'ROE上限',
            min_vwap: 'VWAP下限',
            max_vwap: 'VWAP上限',
            min_per: 'PER下限',
            max_per: 'PER上限',
            min_pbr: 'PBR下限',
            max_pbr: 'PBR上限',
            min_dividend_yield: '配当利回り下限',
            max_dividend_yield: '配当利回り上限',
            // 出来高・価格指標
            min_volume_ratio: '出来高率下限',
            max_volume_ratio: '出来高率上限',
            min_volume_deviation_20: '出来高乖離率(20日)下限',
            max_volume_deviation_20: '出来高乖離率(20日)上限',
            min_volume_deviation_100: '出来高乖離率(100日)下限',
            max_volume_deviation_100: '出来高乖離率(100日)上限',
            min_price_deviation_20: '株価乖離率(20日)下限',
            max_price_deviation_20: '株価乖離率(20日)上限',
            min_price_deviation_100: '株価乖離率(100日)下限',
            max_price_deviation_100: '株価乖離率(100日)上限',
            // RSI・年初来比率指標（新規追加）
            min_rsi: 'RSI下限',
            max_rsi: 'RSI上限',
            min_yearly_high_ratio: '年初来高値比率下限',
            max_yearly_high_ratio: '年初来高値比率上限',
            min_yearly_low_ratio: '年初来安値比率下限',
            max_yearly_low_ratio: '年初来安値比率上限',
            // 信用指標
            min_stock_lending_repayment_ratio: '貸株返済率下限',
            max_stock_lending_repayment_ratio: '貸株返済率上限',
            min_jsf_diff_ratio: '差引前日比率下限',
            max_jsf_diff_ratio: '差引前日比率上限',
            min_short_ratio: '空売り比率下限',
            max_short_ratio: '空売り比率上限',
            min_margin_buying_deviation_20: '信用買残乖離率(20日)下限',
            max_margin_buying_deviation_20: '信用買残乖離率(20日)上限',
            min_margin_buying_volume_ratio: '信用買残高÷出来高(v3)下限',
            max_margin_buying_volume_ratio: '信用買残高÷出来高(v3)上限',
            // 日証金関連（新規追加）
            min_jsf_loan_balance: '日証金融資残高下限（百万株）',
            max_jsf_loan_balance: '日証金融資残高上限（百万株）',
            min_jsf_stock_lending_balance: '日証金貸株残高下限（百万株）',
            max_jsf_stock_lending_balance: '日証金貸株残高上限（百万株）',
            min_jsf_net_balance: '日証金差引残高下限（百万株）',
            max_jsf_net_balance: '日証金差引残高上限（百万株）',
            // その他信用関連
            min_margin_ratio: '信用倍率下限',
            max_margin_ratio: '信用倍率上限',
            margin_lending_only: '貸借銘柄のみ',  // 新規追加
            // 発行済株式数・時価総額
            min_shares_issued: '発行済株式数下限（百万株）',
            max_shares_issued: '発行済株式数上限（百万株）',
            min_market_cap: '時価総額下限（億円）',
            max_market_cap: '時価総額上限（億円）',
            // チャートパターン
            pattern_upper_shadow: '上ヒゲ陽線',
            pattern_doji: '十字線',
            pattern_golden_cross: '価格ゴールデンクロス',
            pattern_doubled_price: '株価倍増',
            pattern_volume_golden_cross: '出来高ゴールデンクロス',
            pattern_vwap_golden_cross: '5日VWAPゴールデンクロス',
            // 移動平均線パターン
            pattern_price_ma25_ma50_ma75: '株価>25MA>50MA>75MA',
            pattern_ma50_ma25_ma75: '50MA>25MA>75MA',
            pattern_ma25_price_ma75: '25MA>株価>75MA',
            pattern_ma50_price_ma75: '50MA>株価>75MA'
        };
        
        let hasFilters = false;
        for (const [key, value] of Object.entries(filters)) {
            if (value && filterLabels[key]) {
                hasFilters = true;
                let displayValue = value;
                if (key === 'target_date') {
                    // YYYYMMDD形式をYYYY-MM-DD形式に変換
                    let dateStr = value;
                    if (value && value.length === 8 && !value.includes('-')) {
                        dateStr = value.substring(0, 4) + '-' + value.substring(4, 6) + '-' + value.substring(6, 8);
                    }
                    
                    const dateObj = new Date(dateStr);
                    
                    // 日付が有効かチェック
                    if (!isNaN(dateObj.getTime())) {
                        displayValue = dateObj.toLocaleDateString('ja-JP', {
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit'
                        });
                    } else {
                        displayValue = value;
                    }
                }
                const tag = $(`<span class="badge bg-primary me-2">${filterLabels[key]}: ${displayValue === true ? '✓' : displayValue}</span>`);
                filterTags.append(tag);
            }
        }
        
        if (hasFilters) {
            $('#activeFilters').removeClass('d-none');
        } else {
            $('#activeFilters').addClass('d-none');
        }
    }
    
    // すべてのフィルターをリセットする関数
    function resetAllFilters() {
        // すべての入力フィールドをクリア
        $('input[type="number"]').val('');
        $('select').val('');
        $('input[type="checkbox"]').prop('checked', false);
        
        // 日付フィルターもリセット
        $('#latestDate').prop('checked', true);
        $('#dateSelect').prop('disabled', true);
        $('#dateSelect').val('');
        selectedDate = null;
        updateSelectedDateDisplay();
        updateDataCount();
        
        // ソート状態もリセット
        currentSortColumn = null;
        currentSortDirection = 'asc';
        updateSortIndicators(null);
        
        // 視覚的フィードバックを更新
        updateFilterVisuals();
    }
    
    // フィルターの視覚的フィードバックを更新する関数
    function updateFilterVisuals() {
        // 値が設定されているフィールドの親要素にクラスを追加
        $('input[type="number"], select').each(function() {
            if ($(this).val()) {
                $(this).closest('.range-group, .mb-3').addClass('filter-active');
            } else {
                $(this).closest('.range-group, .mb-3').removeClass('filter-active');
            }
        });
        
        // チェックされているチェックボックスの親要素にクラスを追加
        $('input[type="checkbox"]').each(function() {
            if ($(this).is(':checked')) {
                $(this).closest('.form-check').addClass('filter-active');
            } else {
                $(this).closest('.form-check').removeClass('filter-active');
            }
        });
    }
    
    // スクリーニング結果をAI分析用に保存する関数
    function saveScreeningResultsForAI(stocks) {
        // テクニカルデータを含む完全なデータを保存
        const resultsWithTechnicalData = stocks.map(stock => {
            return {
                code: stock.code,
                name: stock.name,
                market: stock.market,
                sector: stock.sector,
                price: stock.price,
                change_percent: stock.change_percent,
                volume: stock.volume,
                volume_ratio: stock.volume_ratio,
                volume_deviation: stock.volume_deviation || stock.volume_deviation_20,
                volume_deviation_100: stock.volume_deviation_100,
                price_deviation_5: stock.price_deviation_5 || stock.price_deviation_20,
                price_deviation_100: stock.price_deviation_100,
                stock_lending_repayment_ratio: stock.stock_lending_repayment_ratio,
                jsf_net_balance_change: stock.jsf_net_balance_change,
                jsf_diff_ratio: stock.jsf_diff_ratio,
                short_ratio: stock.short_ratio,
                margin_buying_deviation: stock.margin_buying_deviation || stock.margin_buying_deviation_20,
                roe: stock.roe,
                per: stock.per,
                pbr: stock.pbr,
                dividend_yield: stock.dividend_yield,
                market_cap: stock.market_cap,
                shares_issued: stock.shares_issued,
                vwap: stock.vwap,
                high: stock.high,
                low: stock.low,
                open: stock.open,
                yearly_low: stock.yearly_low,
                yearly_low_date: stock.yearly_low_date,
                // 移動平均線データ
                ma5: stock.ma5,
                wma5: stock.wma5,
                ma10: stock.ma10,
                ma25: stock.ma25,
                ma50: stock.ma50,
                ma75: stock.ma75,
                // テクニカルインジケーター
                rsi14: stock.rsi14,
                macd12_26: stock.macd12_26,
                macd_signal9: stock.macd_signal9,
                macd_histogram: stock.macd_histogram,
                bb_upper20: stock.bb_upper20,
                bb_middle20: stock.bb_middle20,
                bb_lower20: stock.bb_lower20,
                // ゴールデンクロスフラグ
                price_golden_cross: stock.price_golden_cross,
                volume_golden_cross: stock.volume_golden_cross,
                vwap_golden_cross: stock.vwap_golden_cross,
                // チャートパターンフラグ
                has_upper_shadow: stock.has_upper_shadow,
                has_doji: stock.has_doji,
                has_doubled_price: stock.has_doubled_price,
                // 貸借銘柄フラグ（新規追加）
                margin_category: stock.margin_category,
                // データ日付
                stock_date: stock.stock_date
            };
        });
        
        // ローカルストレージに保存
        localStorage.setItem('screeningResults', JSON.stringify(resultsWithTechnicalData));
        localStorage.setItem('screeningResultsTimestamp', new Date().toISOString());
    }
    
    // AI分析ページへ遷移する関数
    window.openAIAnalysis = function() {
        // 新しいタブで開く
        window.open('/ai-analysis', '_blank');
    };
});
