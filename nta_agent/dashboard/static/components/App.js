import StatusHeader from "./StatusHeader.js";
import ResourcePanel from "./ResourcePanel.js";
import CityPanel from "./CityPanel.js";
import MiscPanel from "./MiscPanel.js";
export default {
 components:{ StatusHeader, ResourcePanel, CityPanel, MiscPanel },
 template:`<div><StatusHeader/><main class="grid">
  <ResourcePanel/><CityPanel/><MiscPanel/>
 </main></div>`
};
