(function() {
    let ws;
    let reconnectTimeout;
    const wsStatusEl = document.getElementById('ws-status');
    const currentStateEl = document.getElementById('current-state');
    const stateRingEl = document.getElementById('state-ring');
    const stateCircleEl = document.getElementById('state-circle');
    const transcriptionTextEl = document.getElementById('transcription-text');
    const historyStreamEl = document.getElementById('history-stream');
    const terminalBodyEl = document.getElementById('terminal-body');

    // SVGs progress rings
    const cpuRing = document.getElementById('cpu-ring');
    const memRing = document.getElementById('mem-ring');
    const diskRing = document.getElementById('disk-ring');
    const cpuText = document.getElementById('cpu-text');
    const memText = document.getElementById('mem-text');
    const diskText = document.getElementById('disk-text');

    const circumference = 2 * Math.PI * 34; // r=34

    function setProgress(ring, textEl, percent) {
        if (!ring) return;
        const offset = circumference - (percent / 100 * circumference);
        ring.style.strokeDashoffset = offset;
        textEl.textContent = `${Math.round(percent)}%`;
    }

    // Initialize progress rings
    [cpuRing, memRing, diskRing].forEach(ring => {
        if (ring) {
            ring.style.strokeDasharray = `${circumference} ${circumference}`;
            ring.style.strokeDashoffset = circumference;
        }
    });

    function updateConnectionStatus(connected) {
        const dot = wsStatusEl.querySelector('.pulse-dot');
        const text = wsStatusEl.querySelector('.status-text');
        
        if (connected) {
            dot.className = 'pulse-dot status-online';
            text.textContent = 'ONLINE';
        } else {
            dot.className = 'pulse-dot status-offline';
            text.textContent = 'OFFLINE';
            
            // Revert state visual to offline default
            updateVoiceStateVisual('INACTIVE');
        }
    }

    function connect() {
        if (ws) {
            ws.close();
        }

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
        
        ws = new WebSocket(wsUrl);

        ws.onopen = function() {
            updateConnectionStatus(true);
            addTerminalLine('SYSTEM', 'Connected to dashboard websocket server.');
            if (reconnectTimeout) {
                clearTimeout(reconnectTimeout);
            }
        };

        ws.onmessage = function(event) {
            try {
                const msg = JSON.parse(event.data);
                handleEvent(msg);
            } catch (err) {
                console.error("Error parsing message", err);
            }
        };

        ws.onclose = function() {
            updateConnectionStatus(false);
            addTerminalLine('SYSTEM', 'Disconnected from websocket. Retrying in 3 seconds...', 'warn');
            reconnectTimeout = setTimeout(connect, 3000);
        };

        ws.onerror = function(err) {
            console.error("WebSocket error:", err);
            ws.close();
        };
    }

    // Clean ANSI codes from strings
    function stripAnsi(text) {
        return text.replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
    }

    function handleEvent(event) {
        const type = event.event;
        const data = event.metadata;

        switch (type) {
            case 'health_status':
                updateHealthStatus(data);
                break;
            case 'voice_state_change':
                updateVoiceStateVisual(data.state);
                break;
            case 'speech_heard':
                transcriptionTextEl.textContent = `"${data.corrected_text || data.raw_text}"`;
                break;
            case 'action_parsed':
                handleActionParsed(data);
                break;
            case 'action_result':
                handleActionResult(data);
                break;
            case 'command_executing':
                addTerminalLine('EXEC', `Running: ${data.command}`, 'info');
                break;
            case 'command_executed':
                const outcome = data.returncode === 0 ? 'success' : 'error';
                addTerminalLine('EXEC', `Command returned code ${data.returncode}. Output:\n${stripAnsi(data.output || data.error || '')}`, outcome);
                break;
            case 'console_output':
                const stripped = stripAnsi(data.message);
                if (stripped.trim()) {
                    let level = 'info';
                    if (stripped.includes('✔') || stripped.includes('success')) level = 'success';
                    else if (stripped.includes('⚠') || stripped.includes('warning')) level = 'warn';
                    else if (stripped.includes('✘') || stripped.includes('error') || stripped.includes('failed')) level = 'error';
                    addTerminalLine('CORE', stripped, level);
                }
                break;
            case 'log_message':
                let logLvl = 'debug';
                const lvl = data.level.toLowerCase();
                if (lvl === 'info') logLvl = 'info';
                else if (lvl === 'warning' || lvl === 'warn') logLvl = 'warn';
                else if (lvl === 'error' || lvl === 'critical') logLvl = 'error';
                addTerminalLine(data.logger.toUpperCase(), data.message, logLvl);
                break;
            case 'system_metrics':
                setProgress(cpuRing, cpuText, data.cpu);
                setProgress(memRing, memText, data.memory);
                setProgress(diskRing, diskText, data.disk);
                break;
        }
    }

    function updateHealthStatus(status) {
        const components = ['microphone', 'wake_word', 'whisper', 'elevenlabs', 'browser'];
        components.forEach(comp => {
            const badge = document.getElementById(`health-${comp}`);
            if (badge && status[comp]) {
                const rawVal = status[comp].toLowerCase();
                badge.textContent = status[comp].toUpperCase();
                
                if (rawVal.includes('healthy') || rawVal.includes('active') || rawVal.includes('open')) {
                    badge.className = 'status-badge badge-healthy';
                } else if (rawVal.includes('disabled')) {
                    badge.className = 'status-badge badge-unknown';
                } else if (rawVal.includes('degraded')) {
                    badge.className = 'status-badge badge-degraded';
                } else {
                    badge.className = 'status-badge badge-unavailable';
                }
            }
        });
    }

    function updateVoiceStateVisual(state) {
        currentStateEl.textContent = state;
        
        // Clear old classes
        stateRingEl.className = 'state-ring';
        
        let icon = '🎙';
        
        switch (state) {
            case 'VOICE_IDLE':
                stateRingEl.classList.add('state-cyan');
                icon = '👂';
                break;
            case 'LISTENING':
                stateRingEl.classList.add('state-red');
                icon = '🎤';
                transcriptionTextEl.textContent = "Listening for command...";
                break;
            case 'TRANSCRIBING':
                stateRingEl.classList.add('state-purple');
                icon = '🧠';
                transcriptionTextEl.textContent = "Transcribing speech...";
                break;
            case 'EXECUTING':
                stateRingEl.classList.add('state-purple');
                icon = '⚡';
                break;
            case 'SPEAKING':
                stateRingEl.classList.add('state-green');
                icon = '🔊';
                break;
            case 'WAKE_DETECTED':
                stateRingEl.classList.add('state-cyan');
                icon = '🔔';
                break;
            case 'INACTIVE':
            default:
                icon = '💤';
                transcriptionTextEl.textContent = "Awaiting activation...";
                break;
        }
        
        stateCircleEl.querySelector('.state-icon').textContent = icon;
    }

    // Action Execution logs state
    let activeActionCard = null;

    function handleActionParsed(data) {
        // Clear empty state if present
        const emptyState = historyStreamEl.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        const card = document.createElement('div');
        card.className = 'history-item';
        card.id = `action-${data.action}`;
        
        const timeStr = new Date().toLocaleTimeString();
        
        card.innerHTML = `
            <div class="history-meta">
                <span class="action-badge">${data.action}</span>
                <span class="history-time">${timeStr}</span>
            </div>
            <div class="history-query">Parsing Action Data...</div>
            <div class="history-details">
                <div class="detail-line">Parameters:</div>
                <pre style="font-size: 0.7rem; background: rgba(0,0,0,0.3); padding: 0.4rem; border-radius: 6px; overflow-x: auto; color: var(--text-secondary); max-height: 120px;"><code>${JSON.stringify(data.parameters || {}, null, 2)}</code></pre>
            </div>
        `;
        
        historyStreamEl.insertBefore(card, historyStreamEl.firstChild);
        activeActionCard = card;
    }

    function handleActionResult(data) {
        // Find existing action card or create new one if missed
        let card = activeActionCard;
        if (!card || card.id !== `action-${data.action}`) {
            card = document.getElementById(`action-${data.action}`);
        }
        
        if (!card) {
            // If we missed the parsing event, build a new card
            handleActionParsed({ action: data.action, parameters: {} });
            card = activeActionCard;
        }
        
        if (card) {
            // Update query text (fallback to status if missing)
            const queryEl = card.querySelector('.history-query');
            if (queryEl) {
                queryEl.textContent = `Action Status: ${data.status.toUpperCase()}`;
            }

            // Append status reply
            const isErr = data.status.toLowerCase().includes('failed') || data.status.toLowerCase().includes('exception');
            const respClass = isErr ? 'history-response response-error' : 'history-response';
            
            const respEl = document.createElement('div');
            respEl.className = respClass;
            respEl.textContent = stripAnsi(data.message || 'Execution finished.');
            card.appendChild(respEl);
        }
        
        activeActionCard = null;
    }

    function addTerminalLine(logger, message, type = 'info') {
        const line = document.createElement('div');
        line.className = `terminal-line ${type}-line`;
        
        const timestamp = new Date().toLocaleTimeString();
        line.textContent = `[${timestamp}] [${logger}] ${message}`;
        
        terminalBodyEl.appendChild(line);
        terminalBodyEl.scrollTop = terminalBodyEl.scrollHeight;
        
        // Limit console line buffer size
        while (terminalBodyEl.children.length > 200) {
            terminalBodyEl.removeChild(terminalBodyEl.firstChild);
        }
    }

    // Hook Clears
    document.getElementById('clear-history').onclick = function() {
        historyStreamEl.innerHTML = `
            <div class="empty-state">
                <span class="empty-icon">📂</span>
                <p>History cleared.</p>
            </div>
        `;
    };

    document.getElementById('clear-logs').onclick = function() {
        terminalBodyEl.innerHTML = `<div class="terminal-line system-line">[SYSTEM] Terminal logs cleared.</div>`;
    };

    // Run connection loop
    connect();
})();
