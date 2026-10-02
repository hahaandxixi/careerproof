/* Chart initialization for the competition compliance & AI-depth audit report.
   Palette: Business Blue (single active preset; all colors read from the report's
   --chart-* tokens so page and chart layers stay on the same preset). */
(function () {
  'use strict';

  function token(name, fallback) {
    var value = getComputedStyle(document.documentElement).getPropertyValue(name);
    value = (value || '').trim();
    return value || fallback;
  }

  var el = document.getElementById('chart-ai-depth');
  if (!el) {
    return;
  }

  if (typeof echarts === 'undefined') {
    el.innerHTML = '<p class="figure-empty">图表库未能加载，本图暂不可用；数据同时以表格形式列于上文。</p>';
    return;
  }

  var series1 = token('--chart-series-1', '#0969DA');
  var series2 = token('--chart-series-2', '#8250DF');
  var axisColor = token('--chart-axis', '#5E6B7D');
  var labelColor = token('--chart-label', '#5E6B7D');
  var gridColor = token('--chart-grid', 'rgba(20, 24, 31, 0.12)');
  var tooltipBg = token('--chart-tooltip-bg', '#FFFFFF');

  var categories = [
    '大模型集成',
    'Agent /\n工作流',
    'RAG\n技术应用',
    '多模态能力',
    'AI 安全\n与可控性',
    'MCP /\n工具集成'
  ];
  /* 赛事「AI 技术深度」六项考察点的分值占比，以及本次评估给出的达成度估算（非官方评分）。 */
  var estimated = [6.4, 3.6, 3.6, 1.75, 3.6, 1.4];
  var full = [8, 8, 6, 5, 4, 4];

  var chart = echarts.init(el, null, { renderer: 'svg' });

  chart.setOption({
    animation: false,
    grid: { left: 4, right: 12, top: 52, bottom: 4, containLabel: true },
    legend: {
      top: 0,
      left: 0,
      icon: 'circle',
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 16,
      textStyle: { color: labelColor, fontSize: 12 }
    },
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      backgroundColor: tooltipBg,
      borderColor: gridColor,
      borderWidth: 1,
      textStyle: { color: axisColor, fontSize: 12 },
      axisPointer: { type: 'shadow' },
      valueFormatter: function (value) {
        return value + ' 分';
      }
    },
    xAxis: {
      type: 'category',
      data: categories,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: gridColor, width: 1 } },
      axisLabel: {
        color: labelColor,
        fontSize: 11,
        interval: 0,
        lineHeight: 14,
        formatter: function (value) {
          return value.replace(/\n/g, '');
        }
      }
    },
    yAxis: {
      type: 'value',
      max: 8,
      name: '分值（分）',
      nameTextStyle: { color: labelColor, fontSize: 11, align: 'left' },
      axisLabel: { color: labelColor, fontSize: 11 },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: gridColor, width: 1 } }
    },
    series: [
      {
        name: '自估达成度（估算）',
        type: 'bar',
        data: estimated,
        barMaxWidth: 24,
        barGap: '18%',
        itemStyle: { color: series1, borderRadius: [4, 4, 0, 0] },
        label: {
          show: true,
          position: 'top',
          color: labelColor,
          fontSize: 10
        }
      },
      {
        name: '该项满分',
        type: 'bar',
        data: full,
        barMaxWidth: 24,
        itemStyle: { color: series2, borderRadius: [4, 4, 0, 0] }
      }
    ]
  });

  window.addEventListener('resize', function () {
    chart.resize();
  });
})();
