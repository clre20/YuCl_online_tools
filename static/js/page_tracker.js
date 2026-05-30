/**
 * YuCl 頁面追蹤腳本 (Page Tracker)
 * 負責將使用者訪問數據傳回後端
 */

(function() {
    const startTime = Date.now();
    
    // 1. 頁面載入時立即紀錄一次 (確保基礎訪問被紀錄)
    window.addEventListener('load', function() {
        sendTrackingData(true); // 傳入 true 表示這是「進入頁面」的紀錄
    });

    // 2. 當頁面關閉或隱藏時發送數據 (紀錄停留時間)
    window.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'hidden') {
            sendTrackingData(false);
        }
    });

    // 備用方案：頁面卸載時
    window.addEventListener('beforeunload', function() {
        sendTrackingData(false);
    });

    function sendTrackingData(isInitial) {
        const duration = isInitial ? 0 : (Date.now() - startTime) / 1000;
        const path = window.location.pathname;

        const data = JSON.stringify({
            path: path,
            duration: duration,
            type: isInitial ? 'entry' : 'exit'
        });

        // 避免重複發送相同的 exit 數據
        if (!isInitial && window._tracked_exit) return;
        if (!isInitial) window._tracked_exit = true;

        const blob = new Blob([data], { type: 'application/json' });
        
        // 優先使用 sendBeacon，如果失敗則用 fetch (keepalive)
        if (navigator.sendBeacon) {
            navigator.sendBeacon('/api/sys/track', blob);
        } else {
            fetch('/api/sys/track', {
                method: 'POST',
                body: data,
                headers: { 'Content-Type': 'application/json' },
                keepalive: true
            });
        }
    }
})();
