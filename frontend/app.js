document.addEventListener('DOMContentLoaded', () => {
    const clockElement = document.getElementById('clock');
    const statusElement = document.getElementById('status');
    const progressContainer = document.getElementById('progress-container');
    const progressBar = document.getElementById('progress-bar');
    const connectionStatus = document.getElementById('connection-status');
    const startAlertSound = document.getElementById('start-alert');
    const endAlertSound = document.getElementById('end-alert');
    
    let breaks = [];
    let isBreakActive = false;
    let currentBreak = null;
    let lastBreakId = null;
    let timeOffset = 0; // Zeitdifferenz zwischen Browser und NTP in Sekunden
    
    // Zeit mit NTP-Server synchronisieren
    async function synchronizeTime() {
        try {
            const response = await fetch('/api/ntp-time');
            if (!response.ok) throw new Error('NTP-Anfrage fehlgeschlagen');
            const data = await response.json();
            
            if (data.ntp_time) {
                const now = Math.floor(Date.now() / 1000); // Aktuelle Zeit in Sekunden
                timeOffset = data.ntp_time - now;
                console.log(`Zeitsynchronisation erfolgreich. Offset: ${timeOffset} Sekunden`);
            }
            return true;
        } catch (error) {
            console.error('Zeitsynchronisation fehlgeschlagen:', error);
            return false;
        }
    }
    
    // Konfiguration vom Server abrufen und im localStorage speichern
    async function fetchConfig() {
        try {
            const response = await fetch('/api/config');
            if (!response.ok) throw new Error('Fehler beim Abrufen der Konfiguration');
            const data = await response.json();
            breaks = data.breaks || [];
            
            // Konfiguration im localStorage speichern
            localStorage.setItem('breakConfig', JSON.stringify(data));
            
            document.getElementById('status-connected').style.display = 'inline';
            document.getElementById('status-warning').style.display = 'none';
            document.getElementById('status-error').style.display = 'none';
            return true;
        } catch (error) {
            console.error('Fehler:', error);
            
            // Fallback auf gecachte Konfiguration
            const cachedConfig = localStorage.getItem('breakConfig');
            if (cachedConfig) {
                const data = JSON.parse(cachedConfig);
                breaks = data.breaks || [];
                document.getElementById('status-connected').style.display = 'none';
                document.getElementById('status-warning').style.display = 'inline';
                document.getElementById('status-error').style.display = 'none';
                return true;
            }
            
            document.getElementById('status-connected').style.display = 'none';
            document.getElementById('status-warning').style.display = 'none';
            document.getElementById('status-error').style.display = 'inline';
            return false;
        }
    }
    
    // Uhrzeit aktualisieren mit Zeitkorrektur
    function updateClock() {
        const now = new Date(Date.now() + timeOffset * 1000);
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        clockElement.textContent = `${hours}:${minutes}:${seconds}`;
        
        checkBreakStatus(now);
    }
    
    // Pausenstatus überprüfen
    function checkBreakStatus(now) {
        const currentTime = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
        
        // Aktive Pause finden
        const activeBreak = breaks.find(b => {
            const start = timeToMinutes(b.start);
            const end = timeToMinutes(b.end);
            return currentTime >= start && currentTime <= end;
        });
        
        // Pausenstatus hat sich geändert
        if (activeBreak) {
            if (!currentBreak || activeBreak.id !== currentBreak.id) {
                startBreak(activeBreak, now);
            }
            updateProgressBar(activeBreak, now);
        } else if (currentBreak) {
            endBreak();
        }
    }
    
    // Pause starten
    function startBreak(breakItem, now) {
        isBreakActive = true;
        currentBreak = breakItem;
        document.body.classList.add('break-mode');
        statusElement.textContent = 'PAUSE';
        progressBar.style.width = '100%';
        
        // Ton für Pausenbeginn abspielen
        startAlertSound.play();
        lastBreakId = breakItem.id;
    }
    
    // Pause beenden
    function endBreak() {
        isBreakActive = false;
        currentBreak = null;
        document.body.classList.remove('break-mode');
        statusElement.textContent = '';
        endAlertSound.play(); // Signal für Pausenende
    }
    
    // Fortschrittsbalken aktualisieren
    function updateProgressBar(breakItem, now) {
        const start = timeToMinutes(breakItem.start);
        const end = timeToMinutes(breakItem.end);
        const current = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
        
        // Sicherstellen, dass die Zeit innerhalb der Pause liegt
        if (current < start) return;
        if (current > end) return;
        
        const totalDuration = end - start;
        const elapsed = current - start;
        const remaining = totalDuration - elapsed;
        const percentage = Math.min(100, Math.max(0, (remaining / totalDuration) * 100));
        
        progressBar.style.width = `${percentage}%`;
    }
    
    // Zeitstring in Minuten umwandeln (z.B. "10:15" → 615)
    function timeToMinutes(timeStr) {
        const [hours, minutes] = timeStr.split(':').map(Number);
        return hours * 60 + minutes;
    }
    
    // Initialisierung
    Promise.all([synchronizeTime(), fetchConfig()])
        .then(([timeSuccess, configSuccess]) => {
            if (timeSuccess && configSuccess) {
                updateClock();
                setInterval(updateClock, 1000);
            }
        });
    
    // Alle 5 Minuten Konfiguration aktualisieren und Zeit synchronisieren
    setInterval(() => {
        fetchConfig();
        synchronizeTime();
    }, 300000);
});