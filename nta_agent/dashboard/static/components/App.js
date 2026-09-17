import StatusHeader from "./StatusHeader.js";
import ResourcePanel from "./ResourcePanel.js";
import CityPanel from "./CityPanel.js";
import MiscPanel from "./MiscPanel.js";
import ArmiesPanel from "./ArmiesPanel.js";
import EventsPanel from "./EventsPanel.js";
export default {
 components:{ StatusHeader, ResourcePanel, CityPanel, MiscPanel, ArmiesPanel, EventsPanel },
 template:`<div><StatusHeader/><main class="grid">
  <ResourcePanel/><CityPanel/><MiscPanel/><ArmiesPanel/><EventsPanel/>
 </main></div>`
};
