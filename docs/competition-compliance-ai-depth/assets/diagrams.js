/* Mermaid bootstrap for the analysis-pipeline diagram.
   Structural diagrams use resolved page/brand and semantic colors, never the
   chart-series palette. Values below are the report's Business Blue tokens. */
(function () {
  'use strict';

  if (typeof mermaid === 'undefined') {
    return;
  }

  var nodes = document.querySelectorAll('.mermaid');
  if (!nodes.length) {
    return;
  }

  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'loose',
    theme: 'base',
    fontFamily: "'Instrument Sans', 'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif",
    flowchart: { curve: 'basis', padding: 16, useMaxWidth: true, nodeSpacing: 40, rankSpacing: 44 },
    themeVariables: {
      fontSize: '14px',
      primaryColor: '#EEF4FD',
      primaryTextColor: '#0B2E5C',
      primaryBorderColor: '#0969DA',
      secondaryColor: '#F7F9FC',
      secondaryTextColor: '#14181F',
      secondaryBorderColor: '#D6DEE9',
      tertiaryColor: '#FFFFFF',
      tertiaryTextColor: '#14181F',
      tertiaryBorderColor: '#D6DEE9',
      lineColor: '#93A0B1',
      textColor: '#14181F',
      clusterBkg: '#F7F9FC',
      clusterBorder: '#D6DEE9',
      edgeLabelBackground: '#FFFFFF'
    }
  });

  mermaid.run({ nodes: nodes });
})();
