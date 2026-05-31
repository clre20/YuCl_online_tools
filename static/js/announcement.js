/**
 * YuCl 全站公告動態載入腳本 (懸浮小卡堆疊版 - 右上角 & 依序滑入/滑出 & 5秒自動倒數 & 懸浮暫停 & 手動關閉靜音1分鐘)
 * 實現多個公告時「一個一個出來，一個一個回去」的瀑布流層疊動畫效果。
 */
(function() {
    document.addEventListener("DOMContentLoaded", function() {
        fetch("/api/sys/announcement")
            .then(response => {
                if (!response.ok) throw new Error("Network response was not ok");
                return response.json();
            })
            .then(data => {
                if (data.status === "success" && data.announcements && data.announcements.length > 0) {
                    // 篩選公告：檢查是否被手動關閉過，且還在 1 分鐘的靜音期內
                    const activeAnnouncements = data.announcements.filter(ann => {
                        const closedExpiry = localStorage.getItem(`yucl_closed_ann_expiry_${ann.id}`);
                        if (closedExpiry) {
                            const expiryTime = parseInt(closedExpiry, 10);
                            if (Date.now() < expiryTime) {
                                return false; // 還在一分鐘的靜音期內，不顯示
                            }
                        }
                        return true;
                    });

                    if (activeAnnouncements.length === 0) return;

                    // 1. 注入 CSS 樣式 (使用 both 填滿模式，在動畫延遲時先隱藏)
                    if (!document.getElementById("yucl-ann-styles")) {
                        const style = document.createElement("style");
                        style.id = "yucl-ann-styles";
                        style.innerHTML = `
                            #yucl-ann-container {
                                position: fixed;
                                top: 24px;
                                right: 24px;
                                width: 320px;
                                display: flex;
                                flex-direction: column;
                                gap: 12px;
                                z-index: 999999;
                                pointer-events: none;
                            }
                            
                            .yucl-ann-card {
                                background: rgba(15, 15, 18, 0.88);
                                backdrop-filter: blur(16px);
                                -webkit-backdrop-filter: blur(16px);
                                border: 1px solid rgba(255, 255, 255, 0.08);
                                border-left: 4px solid #00d2ff;
                                border-radius: 16px;
                                color: #ffffff;
                                padding: 16px 20px 20px 20px;
                                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "Noto Sans TC", sans-serif;
                                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
                                box-sizing: border-box;
                                width: 100%;
                                pointer-events: auto;
                                animation: yuclAnnSlideIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
                                display: flex;
                                flex-direction: column;
                                gap: 8px;
                                transition: transform 0.3s ease, opacity 0.3s ease;
                                position: relative;
                                overflow: hidden;
                            }

                            @keyframes yuclAnnSlideIn {
                                from { transform: translateX(120%); opacity: 0; }
                                to { transform: translateX(0); opacity: 1; }
                            }

                            @keyframes yuclAnnSlideOut {
                                from { transform: translateX(0); opacity: 1; }
                                to { transform: translateX(120%); opacity: 0; }
                            }

                            .yucl-ann-header {
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
                                font-size: 13px;
                                font-weight: 700;
                                letter-spacing: 0.5px;
                                text-transform: uppercase;
                            }

                            .yucl-ann-title {
                                display: flex;
                                align-items: center;
                                gap: 6px;
                            }

                            .yucl-ann-close-btn {
                                background: transparent;
                                border: none;
                                color: rgba(255, 255, 255, 0.5);
                                font-size: 18px;
                                cursor: pointer;
                                padding: 0;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                transition: color 0.2s, transform 0.2s;
                                line-height: 1;
                            }

                            .yucl-ann-close-btn:hover {
                                color: #ffffff;
                                transform: scale(1.1);
                            }

                            .yucl-ann-body {
                                font-size: 13.5px;
                                line-height: 1.6;
                                font-weight: 400;
                                color: rgba(255, 255, 255, 0.9);
                                word-break: break-word;
                            }

                            .yucl-ann-body a {
                                color: #00d2ff;
                                text-decoration: underline;
                                font-weight: 600;
                                transition: opacity 0.2s;
                            }

                            .yucl-ann-body a:hover {
                                opacity: 0.8;
                            }

                            /* 5秒倒數進度條 */
                            .yucl-ann-progress {
                                position: absolute;
                                bottom: 0;
                                left: 0;
                                height: 3.5px;
                                width: 100%;
                                transform-origin: left;
                                transform: scaleX(1);
                                transition: transform 0.05s linear;
                            }

                            /* 樣式類型調色 */
                            .yucl-ann-card.card-info {
                                border-left-color: #00d2ff;
                                box-shadow: 0 10px 30px rgba(0, 210, 255, 0.15);
                            }
                            .yucl-ann-card.card-info .yucl-ann-title { color: #00d2ff; }
                            .yucl-ann-card.card-info .yucl-ann-progress { background: #00d2ff; }

                            .yucl-ann-card.card-warning {
                                border-left-color: #f1c40f;
                                box-shadow: 0 10px 30px rgba(241, 196, 15, 0.15);
                            }
                            .yucl-ann-card.card-warning .yucl-ann-title { color: #f1c40f; }
                            .yucl-ann-card.card-warning .yucl-ann-progress { background: #f1c40f; }

                            .yucl-ann-card.card-danger {
                                border-left-color: #ff0055;
                                box-shadow: 0 10px 30px rgba(255, 0, 85, 0.15);
                            }
                            .yucl-ann-card.card-danger .yucl-ann-title { color: #ff0055; }
                            .yucl-ann-card.card-danger .yucl-ann-progress { background: #ff0055; }

                            .yucl-ann-card.card-success {
                                border-left-color: #2ecc71;
                                box-shadow: 0 10px 30px rgba(46, 204, 113, 0.15);
                            }
                            .yucl-ann-card.card-success .yucl-ann-title { color: #2ecc71; }
                            .yucl-ann-card.card-success .yucl-ann-progress { background: #2ecc71; }

                            @media (max-width: 576px) {
                                #yucl-ann-container {
                                    top: 12px;
                                    right: 12px;
                                    left: auto;
                                    width: 280px;
                                    max-width: calc(100vw - 24px);
                                    gap: 8px;
                                }
                                .yucl-ann-card {
                                    padding: 12px 14px 14px 14px;
                                    font-size: 12.5px;
                                    border-radius: 12px;
                                }
                                .yucl-ann-close-btn {
                                    font-size: 22px;
                                    width: 24px;
                                    height: 24px;
                                }
                                .yucl-ann-body {
                                    font-size: 12px;
                                    line-height: 1.5;
                                }
                                .yucl-ann-header {
                                    font-size: 12px;
                                }
                            }
                        `;
                        document.head.appendChild(style);
                    }

                    // 2. 建立或取得容器
                    let container = document.getElementById("yucl-ann-container");
                    if (!container) {
                        container = document.createElement("div");
                        container.id = "yucl-ann-container";
                        document.body.appendChild(container);
                    }

                    // 3. 建立計時追蹤陣列
                    const cardsData = [];
                    const staggerDelay = 250; // 每個公告之間的出現延遲 (毫秒) - 改為 250ms 實現「出來一半下個就滑出」

                    // 4. 渲染每一則公告，並套用漸進延遲
                    activeAnnouncements.forEach((ann, index) => {
                        const card = document.createElement("div");
                        card.className = `yucl-ann-card card-${ann.type}`;
                        // 設定動畫延遲時間，實現一個接一個滑出的效果
                        card.style.animationDelay = `${(index * staggerDelay) / 1000}s`;

                        let iconClass = "fas fa-info-circle";
                        let titleText = "系統公告";
                        if (ann.type === "warning") {
                            iconClass = "fas fa-exclamation-triangle";
                            titleText = "重要警告";
                        } else if (ann.type === "danger") {
                            iconClass = "fas fa-exclamation-circle";
                            titleText = "緊急通知";
                        } else if (ann.type === "success") {
                            iconClass = "fas fa-check-circle";
                            titleText = "更新通知";
                        }

                        card.innerHTML = `
                            <div class="yucl-ann-header">
                                <span class="yucl-ann-title">
                                    <i class="${iconClass}"></i> <b>${titleText}</b>
                                </span>
                                <button type="button" class="yucl-ann-close-btn" aria-label="關閉公告">&times;</button>
                            </div>
                            <div class="yucl-ann-body">${ann.content}</div>
                            <div class="yucl-ann-progress"></div>
                        `;

                        // 關閉小卡函數
                        const closeCardFn = (isManual) => {
                            card.style.animation = "yuclAnnSlideOut 0.4s cubic-bezier(0.16, 1, 0.3, 1) both";
                            setTimeout(() => {
                                card.remove();
                                if (container.children.length === 0) {
                                    container.remove();
                                }
                            }, 400);

                            if (isManual) {
                                localStorage.setItem(`yucl_closed_ann_expiry_${ann.id}`, Date.now() + 60000);
                            }
                            
                            // 自追蹤陣列移除
                            const idx = cardsData.findIndex(item => item.element === card);
                            if (idx !== -1) cardsData.splice(idx, 1);
                        };

                        // 點擊 X 手動關閉
                        const closeBtn = card.querySelector(".yucl-ann-close-btn");
                        closeBtn.addEventListener("click", () => closeCardFn(true));

                        container.appendChild(card);

                        // 加入計時監控 (帶有 delay 與自定義倒數計時)
                        const durationMs = (ann.display_duration || 5) * 1000;
                        cardsData.push({
                            element: card,
                            close: () => closeCardFn(false),
                            delay: index * staggerDelay, // 延遲倒數
                            remaining: durationMs,
                            total: durationMs
                        });
                    });

                    // 5. 中央計時處理核心
                    let lastTime = Date.now();
                    const timerInterval = setInterval(() => {
                        if (cardsData.length === 0) {
                            clearInterval(timerInterval);
                            return;
                        }

                        const now = Date.now();
                        const delta = now - lastTime;
                        lastTime = now;

                        // 懸停時暫停所有計時
                        const isAnyCardHovered = cardsData.some(item => item.element.matches(':hover'));
                        if (isAnyCardHovered) {
                            return;
                        }

                        // 遍歷並處理計時
                        for (let i = cardsData.length - 1; i >= 0; i--) {
                            const item = cardsData[i];
                            
                            // 如果還在等待滑出的延遲期間，先扣除延遲
                            if (item.delay > 0) {
                                item.delay -= delta;
                                if (item.delay < 0) {
                                    item.remaining += item.delay; // 補償微小的溢出時間
                                    item.delay = 0;
                                }
                                continue;
                            }

                            // 正式開始倒數
                            item.remaining -= delta;

                            const progressEl = item.element.querySelector(".yucl-ann-progress");
                            if (progressEl) {
                                const pct = Math.max(0, item.remaining / item.total);
                                progressEl.style.transform = `scaleX(${pct})`;
                            }

                            if (item.remaining <= 0) {
                                item.close();
                            }
                        }
                    }, 50);
                }
            })
            .catch(err => {
                console.warn("[YuCl Announcement] 載入公告小卡失敗:", err);
            });
    });
})();
