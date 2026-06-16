/**
 * EnviroTrust Solar Dashboard Application Logic
 * Integrates AI prediction model and financial simulation with interactive Chart.js charts
 */

// Global state variables
let parksList = [];
let currentMode = 'select'; // 'select' or 'custom'
let amortizationChartInstance = null;
let cashflowChartInstance = null;

// Global helper functions for inline HTML event handlers
window.formatCurrency = function(val) {
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'EUR',
        maximumFractionDigits: 0
    }).format(val);
};

window.formatDecimals = function(val, decs) {
    return parseFloat(val).toLocaleString('de-DE', {
        minimumFractionDigits: decs,
        maximumFractionDigits: decs
    });
};

window.updateSliderBadge = function(id, text) {
    const badge = document.getElementById(`val-${id}`);
    if (badge) {
        badge.textContent = text;
    }
};

window.switchMode = function(mode) {
    currentMode = mode;
    const btnSelect = document.getElementById('btn-select-park');
    const btnCustom = document.getElementById('btn-custom-park');
    const containerSelect = document.getElementById('mode-select-container');
    const containerCustom = document.getElementById('mode-custom-container');
    
    if (mode === 'select') {
        btnSelect.classList.add('active');
        btnCustom.classList.remove('active');
        containerSelect.classList.remove('hidden');
        containerCustom.classList.add('hidden');
    } else {
        btnSelect.classList.remove('active');
        btnCustom.classList.add('active');
        containerSelect.classList.add('hidden');
        containerCustom.classList.remove('hidden');
    }
    updateVisualizer();
};

window.onParkSelectChange = function() {
    updateSelectedParkCoordinates();
    updateVisualizer();
};

/**
 * Updates the visualizer drawing and google maps link based on selected park or custom values
 */
window.updateVisualizer = function() {
    const visualizerEl = document.getElementById('park-visualizer');
    const mapsLinkEl = document.getElementById('google-maps-link');
    if (!visualizerEl) return;
    
    if (currentMode === 'select') {
        const selectEl = document.getElementById('park-select');
        const index = selectEl.value;
        if (index === "" || !parksList[index]) {
            visualizerEl.classList.add('hidden');
            return;
        }
        
        const park = parksList[index];
        visualizerEl.classList.remove('hidden');
        if (mapsLinkEl) mapsLinkEl.classList.remove('hidden');
        
        // Render polygon shape
        drawParkOutline(park.geometry_coords, false);
        
        // Update Maps URL
        mapsLinkEl.href = `https://maps.google.com/?q=${park.lat},${park.lon}&t=k`;
    } else {
        visualizerEl.classList.remove('hidden');
        if (mapsLinkEl) mapsLinkEl.classList.add('hidden');
        
        drawParkOutline(null, true);
    }
};

/**
 * Projects coordinates and draws shape on canvas
 */
function drawParkOutline(polygons, isCustom = false) {
    const canvas = document.getElementById('park-outline-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    if (isCustom) {
        ctx.fillStyle = "#a1a1aa";
        ctx.font = "11px Inter";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("Für einen eigenen Park sind weder Layout-", canvas.width / 2, canvas.height / 2 - 10);
        ctx.fillText("noch Geo- oder Maps-Daten verfügbar.", canvas.width / 2, canvas.height / 2 + 10);
        return;
    }
    
    if (!polygons || polygons.length === 0) {
        ctx.fillStyle = "#52525b";
        ctx.font = "12px Inter";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("Kein Umriss vorhanden", canvas.width / 2, canvas.height / 2);
        return;
    }
    
    // Find geometry bounds
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;
    
    polygons.forEach(polygon => {
        polygon.forEach(pt => {
            const x = pt[0];
            const y = pt[1];
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
        });
    });
    
    const W = maxX - minX;
    const H = maxY - minY;
    
    if (W === 0 || H === 0) return;
    
    const padding = 15;
    const drawW = canvas.width - padding * 2;
    const drawH = canvas.height - padding * 2;
    
    const ratio = W / H;
    const canvasRatio = drawW / drawH;
    
    let S;
    if (ratio > canvasRatio) {
        S = drawW / W;
    } else {
        S = drawH / H;
    }
    
    const offX = padding + (drawW - W * S) / 2;
    const offY = padding + (drawH - H * S) / 2;
    
    const project = (pt) => {
        const cx = offX + (pt[0] - minX) * S;
        // Invert Y axis to point North Up
        const cy = canvas.height - (offY + (pt[1] - minY) * S);
        return [cx, cy];
    };
    
    // Adjust drawing properties based on mode
    if (isCustom) {
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = "#a1a1aa";
        ctx.fillStyle = "rgba(161, 161, 170, 0.05)";
    } else {
        ctx.setLineDash([]);
        ctx.strokeStyle = "#06b6d4";
        ctx.fillStyle = "rgba(6, 182, 212, 0.08)";
    }
    
    ctx.lineWidth = 1.5;
    
    polygons.forEach(polygon => {
        if (polygon.length < 3) return;
        ctx.beginPath();
        const p0 = project(polygon[0]);
        ctx.moveTo(p0[0], p0[1]);
        for (let i = 1; i < polygon.length; i++) {
            const p = project(polygon[i]);
            ctx.lineTo(p[0], p[1]);
        }
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
    });
}

// Main execution after DOM loaded
document.addEventListener('DOMContentLoaded', () => {
    // Initialize slider badges
    initSliderBadges();
    
    // Set initial visibility of O&M cost inputs
    if (window.onOpCostModeChange) {
        window.onOpCostModeChange();
    }
    
    // Load top 100 parks list
    loadParks();
});

/**
 * Handles visibility of operating cost input groups based on selected mode
 */
window.onOpCostModeChange = function() {
    const mode = document.getElementById('param-op-cost-mode').value;
    const customContainer = document.getElementById('op-cost-custom-inputs');
    const modelContainer = document.getElementById('op-cost-model-inputs');
    
    if (mode === 'custom') {
        customContainer.classList.remove('hidden');
        modelContainer.classList.add('hidden');
    } else if (mode === 'model') {
        customContainer.classList.add('hidden');
        modelContainer.classList.remove('hidden');
    } else {
        customContainer.classList.add('hidden');
        modelContainer.classList.add('hidden');
    }
};

/**
 * Sync initial badge text with slider values
 */
function initSliderBadges() {
    const yearsVal = document.getElementById('param-years').value;
    updateSliderBadge('years', `${yearsVal} Jahre`);
    
    const priceVal = document.getElementById('param-price-mw').value;
    updateSliderBadge('price-mw', formatCurrency(priceVal));
    
    const elecVal = document.getElementById('param-elec-price').value;
    updateSliderBadge('elec-price', `${formatDecimals(elecVal, 3)} EUR`);
    
    const degVal = document.getElementById('param-degradation').value;
    updateSliderBadge('degradation', `${degVal} %`);

    // O&M Sliders
    const customOpVal = document.getElementById('param-custom-op-cost').value;
    updateSliderBadge('custom-op-cost', formatCurrency(customOpVal));

    const customOpEscVal = document.getElementById('param-custom-op-escalation').value;
    updateSliderBadge('custom-op-escalation', (customOpEscVal >= 0 ? '+' : '') + formatDecimals(customOpEscVal, 1) + ' %');

    const inflationVal = document.getElementById('param-inflation-rate').value;
    updateSliderBadge('inflation-rate', `${formatDecimals(inflationVal, 1)} %`);
}

/**
 * Setup input listeners for real-time recalculations
 */
/**
 * Updates the coordinates display below the dropdown list
 */
function updateSelectedParkCoordinates() {
    const selectEl = document.getElementById('park-select');
    if (!selectEl) return;
    const index = selectEl.value;
    const coordsVal = document.getElementById('park-coords-val');
    if (coordsVal) {
        if (index !== "" && parksList[index]) {
            const park = parksList[index];
            coordsVal.textContent = `${park.lat.toFixed(4)}° N, ${park.lon.toFixed(4)}° E`;
        } else {
            coordsVal.textContent = '-';
        }
    }
}

/**
 * Fetch top 100 parks from the API
 */
async function loadParks() {
    const selectEl = document.getElementById('park-select');
    try {
        // Show loading state in dropdown
        selectEl.innerHTML = '<option value="">Lade Solarparks...</option>';
        
        const response = await fetch('/api/parks');
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        parksList = await response.json();
        
        // Populate dropdown
        selectEl.innerHTML = '';
        parksList.forEach((park, index) => {
            const option = document.createElement('option');
            option.value = index;
            // Format nice option name
            const label = `${index + 1}. ${park.city || 'Unbekannt'} (${park.area_ha.toFixed(1)} ha, ${park.year})`;
            option.textContent = label;
            selectEl.appendChild(option);
        });
        
        // Auto-select Witznitz (Neukieritzsch, ~162.3 ha) which is usually index 1
        let defaultIndex = parksList.findIndex(p => p.city === 'Neukieritzsch');
        if (defaultIndex === -1 && parksList.length > 0) {
            defaultIndex = 0;
        }
        
        if (parksList.length > 0) {
            selectEl.value = defaultIndex;
        }
        
        // Set coordinates text
        updateSelectedParkCoordinates();
        updateVisualizer();
        
        // Do NOT run initial simulation automatically on load
        // calculateSimulation();
        
    } catch (error) {
        console.error('Error loading parks:', error);
        selectEl.innerHTML = '<option value="">Fehler beim Laden der Parks</option>';
    }
}

/**
 * Trigger simulation by posting inputs to the API
 */
async function calculateSimulation() {
    // 1. Gather inputs
    let area_ha, lat, lon, year;
    
    if (currentMode === 'select') {
        const selectEl = document.getElementById('park-select');
        const index = selectEl.value;
        if (index === "" || !parksList[index]) {
            return; // No park selected
        }
        const park = parksList[index];
        area_ha = park.area_ha;
        lat = park.lat;
        lon = park.lon;
        year = park.year;

        // Update coordinate info on UI
        const coordsVal = document.getElementById('park-coords-val');
        if (coordsVal) {
            coordsVal.textContent = `${lat.toFixed(4)}° N, ${lon.toFixed(4)}° E`;
        }
    } else {
        area_ha = parseFloat(document.getElementById('custom-area').value) || 10.0;
        lat = parseFloat(document.getElementById('custom-lat').value) || 51.3;
        lon = parseFloat(document.getElementById('custom-lon').value) || 10.4;
        year = parseInt(document.getElementById('custom-year').value) || 2023;
    }
    
    // Sliders
    const years = parseInt(document.getElementById('param-years').value);
    const purchase_price_per_mw = parseFloat(document.getElementById('param-price-mw').value);
    const elec_price = parseFloat(document.getElementById('param-elec-price').value);
    const degradation = parseFloat(document.getElementById('param-degradation').value);
    const use_future_projections = document.getElementById('param-future-projections').checked;
    
    // O&M inputs
    const op_cost_mode = document.getElementById('param-op-cost-mode').value;
    const custom_op_cost_per_mw = parseFloat(document.getElementById('param-custom-op-cost').value) || 18000.0;
    const custom_op_cost_escalation = parseFloat(document.getElementById('param-custom-op-escalation').value) || 0.0;
    const inflation_rate = parseFloat(document.getElementById('param-inflation-rate').value) || 2.0;
    const target_profit = parseFloat(document.getElementById('param-target-profit').value) || 0.0;
    
    // Show loading pulse and show spinner overlay
    setKpisLoading(true);
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.classList.remove('hidden');
    }
    
    try {
        const response = await fetch('/api/simulate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                area_ha,
                lat,
                lon,
                year,
                years,
                purchase_price_per_mw,
                elec_price,
                degradation,
                use_future_projections,
                op_cost_mode,
                custom_op_cost_per_mw,
                custom_op_cost_escalation,
                inflation_rate,
                target_profit
            })
        });
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.error || 'Serverfehler');
        }
        
        const data = await response.json();
        
        // Update weather source info on UI
        const wsEl = document.getElementById('weather-source');
        if (wsEl) {
            wsEl.textContent = data.weather_source || '-';
        }
        
        // Update future projections warning badge
        const futureBadge = document.getElementById('future-projections-badge');
        if (futureBadge) {
            if (data.future_projections_active) {
                futureBadge.classList.remove('hidden');
            } else {
                futureBadge.classList.add('hidden');
            }
        }
        
        // Update climate risk scoreboard info
        updateRiskProfile(data.risk_profile);
        
        // Update overheating warning card
        const overheatCard = document.getElementById('overheat-warning-card');
        if (overheatCard) {
            if (data.overheat_info && data.overheat_info.should_warn) {
                document.getElementById('overheat-hours').textContent = data.overheat_info.hours;
                document.getElementById('overheat-cost-annual').textContent = formatCurrency(data.overheat_info.annual_loss_eur);
                document.getElementById('overheat-cost-total').textContent = formatCurrency(data.overheat_info.total_loss_eur);
                overheatCard.classList.remove('hidden');
            } else {
                overheatCard.classList.add('hidden');
            }
        }
        
        // 2. Render KPIs
        updateKPIs(data);
        
        // 3. Render Charts
        renderCharts(data.simulation);
        
        // 4. Render Cashflow Table
        renderTable(data.simulation);
        
    } catch (error) {
        console.error('Error running simulation:', error);
        alert(`Simulationsfehler: ${error.message}`);
    } finally {
        setKpisLoading(false);
        // Hide spinner overlay when completed
        if (overlay) {
            overlay.classList.add('hidden');
        }
    }
}

/**
 * Toggle loading state visual pulse for KPIs
 */
function setKpisLoading(isLoading) {
    const kpis = ['kpi-power', 'kpi-cost', 'kpi-roi', 'kpi-payback'];
    kpis.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            if (isLoading) {
                el.classList.add('loading-pulse');
            } else {
                el.classList.remove('loading-pulse');
            }
        }
    });
}

/**
 * Update the KPI cards with simulation results
 */
function updateKPIs(data) {
    document.getElementById('kpi-power').textContent = `${formatDecimals(data.pred_mw, 2)} MW`;
    document.getElementById('kpi-cost').textContent = formatCurrency(data.total_cost);
    
    // ROI
    const roiEl = document.getElementById('kpi-roi');
    roiEl.textContent = `${formatDecimals(data.roi, 1)} %`;
    if (data.roi >= 100) {
        roiEl.className = 'val-positive';
    } else {
        roiEl.className = '';
    }
    
    // Payback
    const paybackEl = document.getElementById('kpi-payback');
    const simYears = parseInt(document.getElementById('param-years').value) || 20;
    if (data.payback_year) {
        paybackEl.textContent = `${data.payback_year} Jahre`;
        if (data.payback_year <= simYears) {
            paybackEl.className = 'val-positive';
        } else {
            paybackEl.className = 'val-negative';
        }
    } else {
        paybackEl.textContent = 'Nie';
        paybackEl.className = 'val-negative';
    }
}

/**
 * Create or update the Chart.js visualisations
 */
function renderCharts(simulationData) {
    const yearsLabels = simulationData.map(d => `Jahr ${d.year}`);
    const cumProfitData = simulationData.map(d => d.cum_profit);
    const revenueData = simulationData.map(d => d.revenue);
    const opCostData = simulationData.map(d => d.op_cost);
    
    // --- Chart 1: Amortization Line Chart ---
    const ctxAmort = document.getElementById('amortizationChart').getContext('2d');
    
    if (amortizationChartInstance) {
        amortizationChartInstance.destroy();
    }
    
    // Setup clean background gradient for line fill
    const fillGradient = ctxAmort.createLinearGradient(0, 0, 0, 300);
    fillGradient.addColorStop(0, 'rgba(16, 185, 129, 0.08)');
    fillGradient.addColorStop(1, 'rgba(16, 185, 129, 0.0)');

    amortizationChartInstance = new Chart(ctxAmort, {
        type: 'line',
        data: {
            labels: yearsLabels,
            datasets: [{
                label: 'Kumulierter Gewinn',
                data: cumProfitData,
                borderColor: '#10b981',
                borderWidth: 2,
                backgroundColor: fillGradient,
                fill: true,
                tension: 0.25,
                pointBackgroundColor: '#10b981',
                pointBorderColor: '#09090b',
                pointBorderWidth: 1.5,
                pointRadius: 3,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `Gewinn: ${formatCurrency(context.parsed.y)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: '#27272a',
                        drawTicks: false
                    },
                    ticks: {
                        color: '#a1a1aa',
                        font: { family: 'Inter', size: 11 }
                    }
                },
                y: {
                    grid: {
                        color: '#27272a',
                        drawTicks: false
                    },
                    ticks: {
                        color: '#a1a1aa',
                        font: { family: 'Inter', size: 11 },
                        callback: function(value) {
                            if (value >= 1e6) return (value / 1e6).toFixed(1) + ' Mio. €';
                            if (value <= -1e6) return (value / 1e6).toFixed(1) + ' Mio. €';
                            return value.toLocaleString('de-DE') + ' €';
                        }
                    }
                }
            }
        }
    });

    // --- Chart 2: Cashflow Grouped Bar Chart ---
    const ctxCash = document.getElementById('cashflowChart').getContext('2d');
    
    if (cashflowChartInstance) {
        cashflowChartInstance.destroy();
    }
    
    cashflowChartInstance = new Chart(ctxCash, {
        type: 'bar',
        data: {
            labels: yearsLabels,
            datasets: [
                {
                    label: 'Einnahmen',
                    data: revenueData,
                    backgroundColor: '#10b981',
                    borderRadius: 2,
                    barPercentage: 0.75,
                    categoryPercentage: 0.75
                },
                {
                    label: 'Betriebskosten',
                    data: opCostData,
                    backgroundColor: '#ef4444',
                    borderRadius: 2,
                    barPercentage: 0.75,
                    categoryPercentage: 0.75
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#fafafa',
                        font: { family: 'Inter', size: 11, weight: 500 },
                        boxWidth: 12,
                        boxHeight: 12
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `${context.dataset.label}: ${formatCurrency(context.parsed.y)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: '#27272a',
                        drawTicks: false
                    },
                    ticks: {
                        color: '#a1a1aa',
                        font: { family: 'Inter', size: 11 }
                    }
                },
                y: {
                    grid: {
                        color: '#27272a',
                        drawTicks: false
                    },
                    ticks: {
                        color: '#a1a1aa',
                        font: { family: 'Inter', size: 11 },
                        callback: function(value) {
                            if (value >= 1e6) return (value / 1e6).toFixed(1) + ' Mio. €';
                            return value.toLocaleString('de-DE') + ' €';
                        }
                    }
                }
            }
        }
    });
}

/**
 * Render the cashflow spreadsheet table rows
 */
function renderTable(simulationData) {
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '';
    
    simulationData.forEach(row => {
        const tr = document.createElement('tr');
        
        // Year
        const tdYear = document.createElement('td');
        tdYear.textContent = `Jahr ${row.year}`;
        tr.appendChild(tdYear);
        
        // Production
        const tdProd = document.createElement('td');
        tdProd.textContent = `${formatDecimals(row.production_mwh, 1)} MWh`;
        tr.appendChild(tdProd);
        
        // Revenue
        const tdRev = document.createElement('td');
        tdRev.textContent = formatCurrency(row.revenue);
        tr.appendChild(tdRev);
        
        // O&M Costs
        const tdCost = document.createElement('td');
        tdCost.textContent = formatCurrency(row.op_cost);
        tr.appendChild(tdCost);
        
        // Net Profit (Reingewinn)
        const tdNet = document.createElement('td');
        tdNet.textContent = formatCurrency(row.net_profit);
        if (row.net_profit >= 0) {
            tdNet.className = 'val-positive';
        } else {
            tdNet.className = 'val-negative';
        }
        tr.appendChild(tdNet);
        
        // Cumulative Profit
        const tdCum = document.createElement('td');
        tdCum.textContent = formatCurrency(row.cum_profit);
        if (row.cum_profit >= 0) {
            tdCum.className = 'val-positive';
        } else {
            tdCum.className = 'val-negative';
        }
        tr.appendChild(tdCum);
        
        tbody.appendChild(tr);
    });
}

/**
 * Updates the climate risk profile scorecard
 */
function updateRiskProfile(risk) {
    if (!risk) return;
    
    const overallVal = risk.overall_risk;
    const overallEl = document.getElementById('risk-overall-val');
    const gaugeCircle = document.querySelector('.overall-risk-gauge');
    const gaugeBar = document.getElementById('risk-overall-bar');
    
    if (overallEl) {
        overallEl.textContent = overallVal.toFixed(1);
    }
    
    if (gaugeBar) {
        gaugeBar.style.height = `${overallVal * 10}%`;
    }
    
    if (gaugeCircle) {
        gaugeCircle.classList.remove('risk-low', 'risk-medium', 'risk-high');
        if (overallVal >= 7.0) {
            gaugeCircle.classList.add('risk-low'); // Good safety -> Green
        } else if (overallVal >= 4.0) {
            gaugeCircle.classList.add('risk-medium'); // Moderate safety -> Amber
        } else {
            gaugeCircle.classList.add('risk-high'); // Poor safety -> Red
        }
    }
    
    // Update individual bar gauges
    updateRiskBar('air', risk.air_quality);
    updateRiskBar('flood', risk.flood_risk);
    updateRiskBar('wildfire', risk.wildfire_risk);
    updateRiskBar('wind', risk.wind_risk);
    updateRiskBar('heat', risk.heat_risk);
    
    // Update risk source text
    const sourceEl = document.getElementById('risk-source');
    if (sourceEl) {
        sourceEl.textContent = risk.source || '-';
    }
}

/**
 * Updates a single horizontal risk meter group
 */
function updateRiskBar(id, value) {
    const valText = document.getElementById(`risk-${id}-val`);
    const barFill = document.getElementById(`risk-${id}-bar`);
    
    if (valText) {
        valText.textContent = `${value.toFixed(1)}/10`;
        valText.className = 'risk-badge';
        if (value >= 7.0) {
            valText.classList.add('risk-badge-low'); // Good safety -> Green
        } else if (value >= 4.0) {
            valText.classList.add('risk-badge-medium'); // Moderate safety -> Amber
        } else {
            valText.classList.add('risk-badge-high'); // Poor safety -> Red
        }
    }
    
    if (barFill) {
        const percent = Math.min(100, Math.max(0, value * 10));
        barFill.style.width = `${percent}%`;
        barFill.className = 'risk-bar-fill';
        if (value >= 7.0) {
            barFill.classList.add('bg-low'); // Green
        } else if (value >= 4.0) {
            barFill.classList.add('bg-medium'); // Amber
        } else {
            barFill.classList.add('bg-high'); // Red
        }
    }
}
