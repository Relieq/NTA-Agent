const { test } = require("node:test");
const assert = require("node:assert");
const { arriveFrame } = require("../frames");

// Engine formula (ArtofwarForecastObj.startForecast) for a SUBSEQUENT army i>=1:
//   O = max(1, floor((marchTime_i - marchTime_0) / (1000/FPS))) + tiebreak
// The first-selected army is frame 0 and does NOT go through arriveFrame.
test("arriveFrame follows the engine formula", () => {
  // msPerFrame = 1000/20 = 50.
  assert.strictEqual(arriveFrame(0, 0, 0), 1);      // same marchTime, first extra -> max(1,0)
  assert.strictEqual(arriveFrame(50, 0, 0), 1);     // 50ms later -> floor(1)=1
  assert.strictEqual(arriveFrame(5000, 0, 0), 100); // 5000/50 = 100
  assert.strictEqual(arriveFrame(0, 0, 1), 2);      // 2nd army at same delta -> +tiebreak
});
