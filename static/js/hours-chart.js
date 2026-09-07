// One bar chart, three pages. Data arrives via json_script rather than an API
// call, so there is no second request and no endpoint to secure.
(function () {
  var canvas = document.getElementById('hoursChart');
  if (!canvas || typeof Chart === 'undefined') return;

  var labelsEl = document.getElementById('chartLabels');
  var valuesEl = document.getElementById('chartValues');
  if (!labelsEl || !valuesEl) return;

  new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: JSON.parse(labelsEl.textContent),
      datasets: [{
        label: 'Hours',
        data: JSON.parse(valuesEl.textContent),
        backgroundColor: '#4f7cff',
        borderRadius: 4,
        maxBarThickness: 38
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              var total = ctx.parsed.y;
              var h = Math.floor(total);
              var m = Math.round((total - h) * 60);
              return h + 'h ' + (m < 10 ? '0' : '') + m + 'm';
            }
          }
        }
      },
      scales: {
        y: { beginAtZero: true, ticks: { callback: function (v) { return v + 'h'; } },
             grid: { color: '#eef1f6' } },
        x: { grid: { display: false } }
      }
    }
  });
})();
