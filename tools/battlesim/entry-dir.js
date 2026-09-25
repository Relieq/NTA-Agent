"use strict";
// Which pass point (area edge) an attacking army enters the target cell from —
// a faithful port of the engine's MapHelper.getAddArmyDir / getDirByPoint:
//
//   getAddArmyDir(from, to) = getDirByPoint(getMinDisPoint(fromCell.ownPoints, toCell.ownPoints))
//   getDirByPoint(a, b): d = b - a
//     d.y != 0 && |d.y| >= |d.x|  ->  d.y >= 0 ? 2 : 0      (vertical wins ties)
//     otherwise                   ->  d.x >= 0 ? 3 : 1
//
// and getPassPoints(size) = [ (mid, top), (right, mid), (mid, 0), (0, mid) ].
// All pawns stack at that entry point, so the direction decides who gets hit first.
// The old index-geometry guess (0=right 1=left 2=down 3=up, horizontal on ties)
// disagreed with the server — a 0-death forecast lost a pawn live (2026-09-25).

function pointOf(index, mapWidth) {
  return { x: index % mapWidth, y: Math.floor(index / mapWidth) };
}

// Cells an army's origin occupies: the 2x2 main city (top-left index given) or 1 cell.
function ownPoints(index, mapWidth, mainCityIndex) {
  const m = mainCityIndex;
  if (m != null && m >= 0) {
    const block = [m, m + 1, m + mapWidth, m + mapWidth + 1];
    if (block.includes(index)) return block.map((i) => pointOf(i, mapWidth));
  }
  return [pointOf(index, mapWidth)];
}

// Engine getMinDisPoint(from, to) for a 1-cell target: the from-point nearest to it
// (first wins on ties, strict <).
function nearestPoint(from, to) {
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  let best = from[0];
  let bd = dist(best, to);
  for (const p of from) {
    const d = dist(p, to);
    if (d < bd) { bd = d; best = p; }
  }
  return best;
}

function dirByPoint(a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  if (dy !== 0 && Math.abs(dy) >= Math.abs(dx)) return dy >= 0 ? 2 : 0;
  return dx >= 0 ? 3 : 1;
}

function entryDir(fromIndex, targetIndex, mapWidth, nPassPoints, mainCityIndex) {
  const to = pointOf(targetIndex, mapWidth);
  const from = nearestPoint(ownPoints(fromIndex, mapWidth, mainCityIndex), to);
  const dir = dirByPoint(from, to);
  return nPassPoints > 0 ? dir % nPassPoints : 0;
}

module.exports = { entryDir, dirByPoint, ownPoints };
