import StatusHeader from "./StatusHeader.js";
import Sidebar from "./Sidebar.js";
import ResourcePanel from "./ResourcePanel.js";
import CityPanel from "./CityPanel.js";
import MiscPanel from "./MiscPanel.js";
import ArmiesPanel from "./ArmiesPanel.js";
import DecisionsPanel from "./DecisionsPanel.js";
import EquipmentPanel from "./EquipmentPanel.js";
import ForgePanel from "./ForgePanel.js";
import TerritoryPanel from "./TerritoryPanel.js";
import FortsPanel from "./FortsPanel.js";
import BuildOrderPanel from "./BuildOrderPanel.js";
import BrainChatPanel from "./BrainChatPanel.js";
import EventsPanel from "./EventsPanel.js";
import IntelPanel from "./IntelPanel.js";
import LevelingConfigPanel from "./LevelingConfigPanel.js";
import FarmGroupPanel from "./FarmGroupPanel.js";
import LearningPanel from "./LearningPanel.js";
import SetupPanel from "./SetupPanel.js";
import SettingsPanel from "./SettingsPanel.js";
import { getJSON } from "../api.js";
const { ref, onMounted } = window.Vue;
const TABS=[
 {id:"overview", label:"Tổng quan", icon:"▦"},
 {id:"army",     label:"Quân đội",  icon:"⚔"},
 {id:"territory",label:"Lãnh thổ",  icon:"🗺"},
 {id:"intel",    label:"Cố vấn",    icon:"🧭"},
 {id:"build",    label:"Xây dựng & Chiến thuật", icon:"🛠"},
 {id:"log",      label:"Nhật ký",   icon:"📜"},
 {id:"setup",    label:"Thiết lập & Cài đặt", icon:"⚙"},
];
function loadTab(){ try{ return localStorage.getItem("nta.tab")||"overview"; }catch(e){ return "overview"; } }
export default {
 components:{ StatusHeader, Sidebar, ResourcePanel, CityPanel, MiscPanel, ArmiesPanel,
  DecisionsPanel, EquipmentPanel, ForgePanel, TerritoryPanel, FortsPanel, BuildOrderPanel, BrainChatPanel, EventsPanel, IntelPanel, LevelingConfigPanel, FarmGroupPanel, LearningPanel, SetupPanel, SettingsPanel },
 setup(){
  const activeTab=ref(loadTab());
  function select(id){ activeTab.value=id; try{ localStorage.setItem("nta.tab", id); }catch(e){} }
  // Packaged app, first run: land on Setup until every step passes.
  onMounted(async ()=>{ const s=await getJSON("/api/setup");
   if(s && s.packaged && !s.ready) activeTab.value="setup"; });
  return { TABS, activeTab, select };
 },
 template:`<div><StatusHeader/>
  <div class="shell">
   <Sidebar :tabs="TABS" :active="activeTab" @select="select"/>
   <main class="content">
    <div v-if="activeTab==='overview'" class="grid">
     <ResourcePanel/><CityPanel/><MiscPanel/></div>
    <div v-if="activeTab==='army'" class="grid">
     <ArmiesPanel/><FarmGroupPanel/><LevelingConfigPanel/><DecisionsPanel/><EquipmentPanel/><ForgePanel/></div>
    <div v-show="activeTab==='territory'" class="grid">
     <TerritoryPanel/><FortsPanel/></div>
    <div v-if="activeTab==='intel'" class="grid">
     <IntelPanel/><LearningPanel/></div>
    <div v-if="activeTab==='build'" class="grid">
     <BuildOrderPanel/><BrainChatPanel/></div>
    <div v-if="activeTab==='log'" class="grid">
     <EventsPanel/></div>
    <div v-if="activeTab==='setup'" class="grid">
     <SetupPanel/><SettingsPanel/></div>
   </main>
  </div></div>`
};
