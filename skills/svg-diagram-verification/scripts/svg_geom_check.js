// svg_geom_check.js — 整段粘进 browser_console 的 expression 执行。
// 前提：页面已打开且含单个 <svg>。返回 JSON：outOfCanvas / overlaps / textOutOfRange。
(() => {
  const svg = document.querySelector('svg');
  if (!svg) return JSON.stringify({error: 'no svg found on page'});
  const vb = svg.viewBox.baseVal;
  const rects = [...svg.querySelectorAll('rect')]
    .filter(r => r.getAttribute('rx'))   // 组件框；背景/图案 rect 无 rx，自动排除
    .map(r => ({x:+r.getAttribute('x'), y:+r.getAttribute('y'),
                w:+r.getAttribute('width'), h:+r.getAttribute('height')}));
  // 1) 越界
  const outOfCanvas = rects.filter(b =>
    b.x < 0 || b.y < 0 || b.x + b.w > vb.width || b.y + b.h > vb.height);
  // 2) 重叠（跳过同几何的双 rect 遮罩对——architecture-diagram 的预期模式）
  const overlaps = [];
  for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
    const a = rects[i], b = rects[j];
    if (a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y) {
      if (a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h) continue;
      overlaps.push([a, b]);
    }
  }
  // 3) 文字越界（仅查 x 锚点；软溢出需 vision）
  const texts = [...svg.querySelectorAll('text')];
  const textOutOfRange = texts.filter(t => {
    const tx = +t.getAttribute('x');
    return tx < 0 || tx > vb.width;
  }).length;
  return JSON.stringify({viewBox: [vb.width, vb.height], boxes: rects.length,
    outOfCanvas, overlaps: overlaps.length, overlapPairs: overlaps.slice(0, 5),
    textOutOfRange, totalText: texts.length});
})()
