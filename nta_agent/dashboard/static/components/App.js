import StatusHeader from "./StatusHeader.js";
import ResourcePanel from "./ResourcePanel.js";
import CityPanel from "./CityPanel.js";
import MiscPanel from "./MiscPanel.js";
import ArmiesPanel from "./ArmiesPanel.js";
import DecisionsPanel from "./DecisionsPanel.js";
import EquipmentPanel from "./EquipmentPanel.js";
import TerritoryPanel from "./TerritoryPanel.js";
import FortsPanel from "./FortsPanel.js";
import BuildOrderPanel from "./BuildOrderPanel.js";
import BrainChatPanel from "./BrainChatPanel.js";
import EventsPanel from "./EventsPanel.js";
export default {
 components:{ StatusHeader, ResourcePanel, CityPanel, MiscPanel, ArmiesPanel, DecisionsPanel,
  EquipmentPanel, TerritoryPanel, FortsPanel, BuildOrderPanel, BrainChatPanel, EventsPanel },
 template:`<div><StatusHeader/><main class="grid">
  <ResourcePanel/><CityPanel/><MiscPanel/><ArmiesPanel/><DecisionsPanel/><EquipmentPanel/>
  <TerritoryPanel/><FortsPanel/><BuildOrderPanel/><BrainChatPanel/><EventsPanel/>
 </main></div>`
};
