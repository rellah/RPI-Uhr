document.addEventListener("DOMContentLoaded", () => {
    const clockElement = document.getElementById("clock");
    const statusElement = document.getElementById("status");
    const progressBar = document.getElementById("progress-bar");
    const startAlertSound = document.getElementById("start-alert");
    const endAlertSound = document.getElementById("end-alert");

    let breaks = [];
    let currentBreak = null;
    let ntpReference = null; // Holds the last successful NTP sync
    let fallbackOffsetSeconds = 0; // Offset fallback when only system time is available
    let lastSystemTick = Date.now();
    let pendingTimeSync = null;

    function getSynchronizedDate() {
        if (ntpReference) {
            const elapsedMs = performance.now() - ntpReference.perfMs;
            return new Date(ntpReference.unixSeconds * 1000 + elapsedMs);
        }

        return new Date(Date.now() + fallbackOffsetSeconds * 1000);
    }

    async function synchronizeTime() {
        if (pendingTimeSync) {
            return pendingTimeSync;
        }

        const syncPromise = (async () => {
            try {
                const response = await fetch("/api/ntp-time", { cache: "no-store" });
                if (!response.ok) {
                    throw new Error("NTP request failed");
                }

                const data = await response.json();
                if (data.ntp_time === undefined) {
                    throw new Error("Missing ntp_time value");
                }

                const unixSeconds = Number(data.ntp_time);
                if (!Number.isFinite(unixSeconds)) {
                    throw new Error("Invalid NTP payload");
                }

                const perfNow = performance.now();
                const systemNowSeconds = Math.floor(Date.now() / 1000);
                fallbackOffsetSeconds = unixSeconds - systemNowSeconds;
                ntpReference = {
                    unixSeconds,
                    perfMs: perfNow
                };

                console.log(`Zeitsynchronisation erfolgreich. Offset: ${fallbackOffsetSeconds} Sekunden`);
                return true;
            } catch (error) {
                console.error("Zeitsynchronisation fehlgeschlagen:", error);
                return false;
            } finally {
                pendingTimeSync = null;
            }
        })();

        pendingTimeSync = syncPromise;
        return syncPromise;
    }

    async function fetchConfig() {
        try {
            const response = await fetch("/api/config", { cache: "no-store" });
            if (!response.ok) {
                throw new Error("Fehler beim Abrufen der Konfiguration");
            }

            const data = await response.json();
            breaks = data.breaks || [];

            localStorage.setItem("breakConfig", JSON.stringify(data));

            document.getElementById("status-connected").style.display = "inline";
            document.getElementById("status-warning").style.display = "none";
            document.getElementById("status-error").style.display = "none";
            return true;
        } catch (error) {
            console.error("Fehler:", error);

            const cachedConfig = localStorage.getItem("breakConfig");
            if (cachedConfig) {
                const data = JSON.parse(cachedConfig);
                breaks = data.breaks || [];
                document.getElementById("status-connected").style.display = "none";
                document.getElementById("status-warning").style.display = "inline";
                document.getElementById("status-error").style.display = "none";
                return true;
            }

            document.getElementById("status-connected").style.display = "none";
            document.getElementById("status-warning").style.display = "none";
            document.getElementById("status-error").style.display = "inline";
            return false;
        }
    }

    function updateClock() {
        const systemNow = Date.now();
        if (Math.abs(systemNow - (lastSystemTick + 1000)) > 5000) {
            synchronizeTime();
        }
        lastSystemTick = systemNow;

        const now = getSynchronizedDate();
        const hours = String(now.getHours()).padStart(2, "0");
        const minutes = String(now.getMinutes()).padStart(2, "0");
//        const seconds = String(now.getSeconds()).padStart(2, "0");
        clockElement.textContent = `${hours}:${minutes}`;
//        clockElement.textContent = `${hours}:${minutes}:${seconds}`;

        checkBreakStatus(now);
    }

    function checkBreakStatus(now) {
        const currentTime = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;

        const activeBreak = breaks.find(b => {
            const start = timeToMinutes(b.start);
            const end = timeToMinutes(b.end);
            return currentTime >= start && currentTime <= end;
        });

        if (activeBreak) {
            if (!currentBreak || activeBreak.id !== currentBreak.id) {
                startBreak(activeBreak);
            }
            updateProgressBar(activeBreak, now);
        } else if (currentBreak) {
            endBreak();
        }
    }

    function startBreak(breakItem) {
        currentBreak = breakItem;
        document.body.classList.add("break-mode");
        statusElement.textContent = "PAUSE";
        progressBar.style.width = "0%";

        // Play tone for break start
        startAlertSound.play();
    }

    function endBreak() {
        currentBreak = null;
        document.body.classList.remove("break-mode");
        statusElement.textContent = "";
        // Play tone for break end
        endAlertSound.play();
    }

    function updateProgressBar(breakItem, now) {
        const start = timeToMinutes(breakItem.start);
        const end = timeToMinutes(breakItem.end);
        const current = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;

        const totalDuration = end - start;
        if (totalDuration <= 0) {
            progressBar.style.width = "100%";
            return;
        }

        if (current <= start) {
            progressBar.style.width = "0%";
            return;
        }

        if (current >= end) {
            progressBar.style.width = "100%";
            return;
        }

        const elapsed = current - start;
        const fillPercentage = Math.min(100, Math.max(0, (elapsed / totalDuration) * 100));
        progressBar.style.width = `${fillPercentage}%`;
    }

    function timeToMinutes(timeStr) {
        const [hours, minutes] = timeStr.split(":").map(Number);
        return hours * 60 + minutes;
    }

    Promise.all([synchronizeTime(), fetchConfig()])
        .catch((error) => console.error("Initialisierung fehlgeschlagen:", error))
        .finally(() => {
            updateClock();
            setInterval(updateClock, 1000);
        });

    setInterval(async () => {
        await fetchConfig();
        await synchronizeTime();
    }, 300000);
});
