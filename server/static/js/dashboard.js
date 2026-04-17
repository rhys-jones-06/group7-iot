/**
 * LockIn Dashboard JavaScript
 * CM2211 Group 07 — Internet of Things
 *
 * Handles live polling, chart rendering, and pet system for dashboard (F6).
 */

const POLL_INTERVAL = 10000; // 10 seconds

// Chart instances
let trendChart = null;
let heatmapChart = null;

// Pet system state
const petSystem = {
    currentStreak: 0,
    lastMilestoneStreak: 0
};

/**
 * Initialize dashboard on page load
 */
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    updateDashboard();
    initPetAnimations();

    // Poll every 10 seconds (F6: Live session status)
    setInterval(updateDashboard, POLL_INTERVAL);
});

/**
 * Initialize empty charts with new colorful styling
 */
function initCharts() {
    const trendCtx = document.getElementById('trendChart').getContext('2d');
    trendChart = new Chart(trendCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Focus Score',
                    data: [],
                    borderColor: '#FF6B6B',
                    backgroundColor: 'rgba(255, 107, 107, 0.1)',
                    borderWidth: 3,
                    tension: 0.4,
                    pointBackgroundColor: '#FF6B6B',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointRadius: 5,
                    pointHoverRadius: 7,
                    fill: true,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
                filler: { propagate: true },
            },
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    ticks: { color: '#888' },
                    grid: { color: 'rgba(0, 0, 0, 0.05)' },
                },
                x: {
                    ticks: { color: '#888' },
                    grid: { display: false },
                },
            },
        },
    });

    const heatmapCtx = document.getElementById('heatmapChart').getContext('2d');
    heatmapChart = new Chart(heatmapCtx, {
        type: 'bar',
        data: {
            labels: Array.from({ length: 24 }, (_, i) =>
                `${i}:00`
            ),
            datasets: [
                {
                    label: 'Distractions',
                    data: Array(24).fill(0),
                    backgroundColor: (context) => {
                        const value = context.parsed.y || 0;
                        if (value === 0) return 'rgba(200, 200, 200, 0.3)';
                        if (value < 2) return 'rgba(149, 231, 125, 0.7)';
                        if (value < 5) return 'rgba(255, 230, 109, 0.7)';
                        return 'rgba(255, 107, 107, 0.7)';
                    },
                    borderRadius: 5,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#888' },
                    grid: { color: 'rgba(0, 0, 0, 0.05)' },
                },
                x: {
                    ticks: { color: '#888' },
                    grid: { display: false },
                },
            },
        },
    });
}

/**
 * Fetch and update all dashboard data
 */
async function updateDashboard() {
    try {
        await Promise.all([
            updateSummary(),
            updateTrend(),
            updateHeatmap(),
            updateSessions(),
        ]);
    } catch (error) {
        console.error('Error updating dashboard:', error);
    }
}

/**
 * Update summary stats cards
 */
async function updateSummary() {
    const response = await fetch('/api/stats/summary');
    if (!response.ok) throw new Error('Failed to fetch summary');

    const data = await response.json();

    document.getElementById('streak-days').textContent = data.current_streak;
    document.getElementById('sessions-today').textContent = data.total_sessions_today;
    document.getElementById('focus-mins-today').textContent = Math.round(data.total_focus_mins_today);
    document.getElementById('focus-score-week').textContent = data.avg_focus_score_this_week.toFixed(0);
    document.getElementById('best-focus').textContent = data.best_focus_score.toFixed(0);

    // Pet system: Update based on streak
    petSystem.currentStreak = data.current_streak;
    updatePetStatus();

    // Celebrate milestone streaks
    if (data.current_streak > 0 && data.current_streak % 7 === 0 && data.current_streak !== petSystem.lastMilestoneStreak) {
        celebrateStreak(data.current_streak);
        petSystem.lastMilestoneStreak = data.current_streak;
    }
}

/**
 * Update trend chart (14-day focus score)
 */
async function updateTrend() {
    const response = await fetch('/api/stats/trend?days=14');
    if (!response.ok) throw new Error('Failed to fetch trend');

    const data = await response.json();
    const trend = data.trend;

    trendChart.data.labels = trend.map((d) => {
        const date = new Date(d.date);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });
    trendChart.data.datasets[0].data = trend.map((d) => d.avg_focus_score);
    trendChart.update();
}

/**
 * Update heatmap chart and insight
 */
async function updateHeatmap() {
    const response = await fetch('/api/stats/heatmap');
    if (!response.ok) throw new Error('Failed to fetch heatmap');

    const data = await response.json();

    heatmapChart.data.datasets[0].data = data.heatmap.map((h) => h.count);
    heatmapChart.update();

    document.getElementById('heatmap-insight').textContent = data.insight;
}

/**
 * Update recent sessions table
 */
async function updateSessions() {
    const response = await fetch('/api/sessions?limit=10');
    if (!response.ok) throw new Error('Failed to fetch sessions');

    const data = await response.json();
    const tbody = document.getElementById('sessions-tbody');

    if (data.sessions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="loading">No sessions yet. Start studying!</td></tr>';
        return;
    }

    tbody.innerHTML = data.sessions
        .map((session) => {
            const date = new Date(session.timestamp);
            const dateStr = date.toLocaleDateString('en-US');
            const timeStr = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
            const score = session.focus_score.toFixed(0);
            const scoreColor = score >= 80 ? '#95E77D' : score >= 60 ? '#FFE66D' : score >= 40 ? '#FF8E8E' : '#FF6B6B';

            return `
                <tr>
                    <td>${dateStr} ${timeStr}</td>
                    <td>${session.duration_mins.toFixed(1)} min</td>
                    <td>${session.distraction_count}</td>
                    <td><strong style="color: ${scoreColor}">${score}</strong></td>
                </tr>
            `;
        })
        .join('');
}

/**
 * Pet System Functions
 */

function initPetAnimations() {
    const svg = document.getElementById('pet-svg');
    if (!svg) return;

    // Pet idle animations
    setInterval(() => {
        const animations = ['bounce', 'wiggle'];
        const anim = animations[Math.floor(Math.random() * animations.length)];
        animatePet(anim);
    }, 8000);
}

function animatePet(type) {
    const svg = document.getElementById('pet-svg');
    if (!svg) return;

    svg.style.animation = 'none';
    setTimeout(() => {
        if (type === 'bounce') {
            svg.style.animation = 'bounce 0.6s ease-in-out';
        } else if (type === 'wiggle') {
            svg.style.animation = 'wiggle 0.6s ease-in-out';
        }
    }, 10);
}

function updatePetStatus() {
    const streak = petSystem.currentStreak;
    const statusEl = document.getElementById('pet-status');

    if (streak === 0) {
        statusEl.textContent = '😊 Ready for today\'s session!';
    } else if (streak > 10) {
        statusEl.textContent = '🎉 Thriving from your dedication!';
    } else if (streak > 5) {
        statusEl.textContent = '😊 Growing stronger with each session!';
    } else if (streak > 1) {
        statusEl.textContent = '😸 Building momentum!';
    } else {
        statusEl.textContent = '😊 Great start!';
    }
}

function celebrateStreak(streak) {
    const hearts = document.getElementById('hearts');
    if (hearts) {
        hearts.style.opacity = '1';
        setTimeout(() => {
            hearts.style.opacity = '0';
        }, 2000);
    }

    launchConfetti();
    console.log(`🎉 Streak milestone: ${streak} days!`);
}

function launchConfetti() {
    const emojis = ['🎉', '🎊', '✨', '⭐', '🔥', '💜'];
    for (let i = 0; i < 50; i++) {
        const confetti = document.createElement('div');
        confetti.className = 'confetti';
        confetti.innerHTML = emojis[Math.floor(Math.random() * emojis.length)];
        confetti.style.left = Math.random() * window.innerWidth + 'px';
        confetti.style.top = '-10px';
        confetti.style.fontSize = (Math.random() * 20 + 20) + 'px';
        confetti.style.position = 'fixed';
        confetti.style.pointerEvents = 'none';
        confetti.style.animation = 'confettiFall 3s ease-in forwards';
        document.body.appendChild(confetti);

        setTimeout(() => confetti.remove(), 3000);
    }
}
