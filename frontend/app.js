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
    
    // Konfiguration vom Server abrufen
    async function fetchConfig() {
        try {
            const response = await fetch('/api/config');
            if (!response.ok) throw new Error('Fehler beim Abrufen der Konfiguration');
            const data = await response.json();
            breaks = data.breaks || [];
            connectionStatus.textContent = `Verbunden (v${data.version})`;
            connectionStatus.style.color = '#4CAF50';
            return true;
        } catch (error) {
            console.error('Fehler:', error);
            connectionStatus.textContent = 'Keine Verbindung zum Server';
            connectionStatus.style.color = '#FF5722';
            return false;
        }
    }
    
    // Uhrzeit aktualisieren
    function updateClock() {
        const now = new Date();
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
        document.body.classList.add('break-mode'); // Hintergrundfarbe aktivieren
        statusElement.textContent = 'PAUSE';
        progressContainer.classList.remove('hidden');
        progressBar.style.width = '100%'; // Start bei 100%
        
        // Ton für Pausenbeginn abspielen
        startAlertSound.play();
        lastBreakId = breakItem.id;
    }
    
    // Pause beenden
    function endBreak() {
        isBreakActive = false;
        currentBreak = null;
        document.body.classList.remove('break-mode'); // Hintergrundfarbe deaktivieren
        statusElement.textContent = '';
        progressContainer.classList.add('hidden');
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
    fetchConfig().then(success => {
        if (success) {
            updateClock();
            setInterval(updateClock, 1000);
        }
    });
    
    // Alle 5 Minuten Konfiguration aktualisieren
    setInterval(fetchConfig, 300000);
});