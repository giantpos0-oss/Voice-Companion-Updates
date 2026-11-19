// A transport adapter, not a second reading/navigation implementation.
// Only the chosen tab and its own new popup tabs are exposed to Companion.
class CompanionCDP {
  constructor(api, emit) {
    this.api = api; this.emit = emit; this.tabs = new Map(); this.children = new Map();
    this.autoAttach = false; this.serial = 0; this.aliases = new Map(); this.browserSessions = new Set(); this.allTabs = false;
    // Tabs whose debugger bar the user cancelled. They stay unattached until the user reconnects.
    this.declined = new Set();
  }
  remember(tab, attached = false) {
    if (!Number.isInteger(tab?.id)) throw new Error('No browser tab is available.');
    const prior = this.tabs.get(tab.id);
    if (prior) return prior;
    const item = {tabId:tab.id, attached, sessionId:'vc-tab-'+(++this.serial), announced:false, info:null};
    this.tabs.set(tab.id,item); return item;
  }
  async attach(item) {
    if(item.attaching)return item.attaching;
    item.attaching=this._attach(item);
    try{return await item.attaching;}finally{item.attaching=null;}
  }
  async _attach(item) {
    if (!item.attached) {
      // A tab this link attached before (then lost track of, as on a trip to a chrome:// page)
      // is still ours: Chrome says it is already attached. Go on with it instead of losing the tab.
      try { await this.api.debugger.attach({tabId:item.tabId},'1.3'); }
      catch (error) { if (!/already attached/i.test(String(error?.message || error))) throw error; }
      item.attached = true;
    }
    const {targetInfo} = await this.api.debugger.sendCommand({tabId:item.tabId},'Target.getTargetInfo');
    // Playwright requires a nonempty context label even for the normal profile.
    // This is protocol metadata; it grants no access to other tabs or contexts.
    item.info = {...targetInfo, browserContextId:targetInfo.browserContextId || 'voice-companion-default', attached:true};
    if (!item.announced) {
      item.announced = true;
      this.emit({method:'Target.attachedToTarget',params:{sessionId:item.sessionId,targetInfo:item.info,waitingForDebugger:false}});
    }
    return item;
  }
  source(sessionId) {
    const alias=this.aliases.get(sessionId);
    if (alias !== undefined) return {tabId:alias};
    const item = [...this.tabs.values()].find(t=>t.sessionId === sessionId);
    if (item) return {tabId:item.tabId};
    const tabId = this.children.get(sessionId);
    if (tabId !== undefined) return {tabId,sessionId};
    throw new Error('The selected browser tab or frame disconnected. Reconnect it.');
  }
  event(source, method, params) {
    const item = this.tabs.get(source.tabId);
    if (!item || !item.announced) return;
    if (method === 'Target.attachedToTarget' && params?.sessionId) this.children.set(params.sessionId,source.tabId);
    if (method === 'Target.detachedFromTarget' && params?.sessionId) this.children.delete(params.sessionId);
    this.emit({sessionId:source.sessionId || item.sessionId,method,params});
  }
  removed(tabId) {
    const item = this.tabs.get(tabId);
    if (!item) return;
    this.tabs.delete(tabId);
    for (const [id,owner] of this.children) if (owner === tabId) this.children.delete(id);
    if (item.announced) this.emit({method:'Target.detachedFromTarget',params:{sessionId:item.sessionId,targetId:item.info?.targetId}});
  }
  async created(tab) {
    if (this.declined.has(tab.id)) return;
    if (!this.tabs.has(tab.openerTabId) && !(this.allTabs && /^https?:\/\//i.test(tab.url || ''))) return;
    const item = this.remember(tab);
    if (!this.autoAttach) return;
    // A tab that could not attach yet (still loading, a page Chrome guards) is forgotten, so the
    // next load of the tab tries again. Kept, it was never retried, and Companion could not reach it.
    try { await this.attach(item); }
    catch (error) { if (!item.announced && this.tabs.get(tab.id) === item) this.tabs.delete(tab.id); throw error; }
  }
  // Chrome swaps a tab for a new one when a page it loaded ahead is shown (typing an address).
  async replaced(addedTabId, removedTabId) {
    this.removed(removedTabId);
    const tab = await this.api.tabs.get(addedTabId).catch(()=>null);
    if (tab) await this.created(tab);
  }
  reset() {
    this.autoAttach = false;this.children.clear();this.aliases.clear();this.browserSessions.clear();
    for (const item of this.tabs.values()) item.announced = false;
  }
  async command(message) {
    const {method,params = {},sessionId} = message;
    if (method === 'VoiceCompanion.reset') { this.reset(); return; }
    if (!Number.isInteger(message.id) || typeof method !== 'string') return;
    try {
      const result = await this.dispatch(method,params,sessionId);
      this.emit({id:message.id,...(sessionId?{sessionId}:{}),result:result || {}});
    } catch (error) {
      // CDP errors can contain a submitted value. Keep error text generic, but name the kind of
      // failure from a fixed list, so Companion's log says why (every failure names itself).
      this.emit({id:message.id,...(sessionId?{sessionId}:{}),error:{code:-32000,message:'The browser could not complete '+method+'. The tab may have changed or disconnected.'+CompanionCDP.reason(error)}});
    }
  }
  async dispatch(method,params,sessionId) {
    if (this.browserSessions.has(sessionId)) sessionId=undefined;
    if (!sessionId && method === 'Target.attachToBrowserTarget') {
      const id='vc-browser-'+(++this.serial);this.browserSessions.add(id);return {sessionId:id};
    }
    if (!sessionId && method === 'Target.attachToTarget') {
      const item=[...this.tabs.values()].find(t=>t.info?.targetId===params.targetId);
      if (!item)throw new Error('Unknown browser tab.');
      const id='vc-inspect-'+(++this.serial);this.aliases.set(id,item.tabId);return {sessionId:id};
    }
    if (method === 'Target.detachFromTarget' && this.aliases.has(params.sessionId)) {
      this.aliases.delete(params.sessionId);return {};
    }
    if (!sessionId && method === 'VoiceCompanion.getActiveTarget') {
      const [tab]=await this.api.tabs.query({active:true,lastFocusedWindow:true});
      let item=this.tabs.get(tab?.id);
      // The tab the user is on is not linked yet: link it now rather than answer "unknown".
      if (!item?.info && tab && this.allTabs && this.autoAttach && /^https?:\/\//i.test(tab.url || '') && !this.declined.has(tab.id)) {
        await this.created(tab).catch(()=>{});item=this.tabs.get(tab.id);
      }
      return {targetId:item?.info?.targetId || ''};
    }
    if (!sessionId && method === 'Browser.getVersion') {
      if (!this.tabs.size && this.allTabs)for(const tab of await this.api.tabs.query({}))if(/^https?:\/\//i.test(tab.url||'')&&!this.declined.has(tab.id))this.remember(tab);
      let item;
      for(const candidate of this.tabs.values()) {
        try {if(!candidate.attached){await this.api.debugger.attach({tabId:candidate.tabId},'1.3');candidate.attached=true;}item=candidate;break;}
        catch {this.removed(candidate.tabId);}
      }
      if (!item) throw new Error('Open a normal website tab first.');
      const reply = await this.api.debugger.sendCommand({tabId:item.tabId},'Runtime.evaluate',{expression:'navigator.userAgent',returnByValue:true});
      const agent = String(reply.result?.value || '');
      const version = /(?:Chrome|Chromium)\/([\d.]+)/.exec(agent)?.[1] || '140.0.0.0';
      return {protocolVersion:'1.3',product:'Chrome/'+version,userAgent:agent,revision:'',jsVersion:''};
    }
    if (!sessionId && method === 'Browser.setDownloadBehavior') return {};
    if (!sessionId && method === 'Target.setAutoAttach') {
      this.autoAttach = !!params.autoAttach;
      if (this.autoAttach) await Promise.all([...this.tabs.values()].map(async item=>{
        if(!item.attached){await this.api.debugger.attach({tabId:item.tabId},'1.3');item.attached=true;}
        await this.api.debugger.sendCommand({tabId:item.tabId},'Target.setAutoAttach',{autoAttach:false,waitForDebuggerOnStart:false,flatten:true});
        // A new local driver needs fresh contexts and lifecycle events.
        // Re-enabling an already enabled Runtime does not replay contexts.
        for (const domain of ['Runtime','Page','Network','Log'])
          await this.api.debugger.sendCommand({tabId:item.tabId},domain+'.disable');
        return this.attach(item);
      }).map(promise=>promise.catch(()=>{})));
      return {};
    }
    if (!sessionId && method === 'Target.getTargetInfo') {
      return {targetInfo:{targetId:'voice-companion-browser',type:'browser',title:'',url:'',attached:true}};
    }
    if (!sessionId && method === 'Target.createTarget') {
      const url = params.url || 'about:blank';
      if (!/^(https?:\/\/|about:blank$)/i.test(url)) throw new Error('Unsupported tab address.');
      const tab = await this.api.tabs.create({url});
      const item = await this.attach(this.remember(tab));
      return {targetId:item.info.targetId};
    }
    if (!sessionId && method === 'Target.closeTarget') {
      const item = [...this.tabs.values()].find(t=>t.info?.targetId === params.targetId);
      if (!item) return {success:false};
      await this.api.tabs.remove(item.tabId);return {success:true};
    }
    if (!sessionId && method === 'Target.activateTarget') {
      const item = [...this.tabs.values()].find(t=>t.info?.targetId === params.targetId);
      if (!item) throw new Error('Unknown tab.');
      await this.api.tabs.update(item.tabId,{active:true});return {};
    }
    // Browser-global data and settings are not part of reading the chosen tab.
    if (!sessionId) throw new Error('Unsupported browser-level request.');
    if (!/^(Accessibility|Audits|CSS|DOM|DOMDebugger|DOMSnapshot|Debugger|Emulation|Fetch|IO|Input|Inspector|Log|Network|Overlay|Page|Performance|Profiler|Runtime|Security|Target|WebAudio)\./.test(method)) throw new Error('Unsupported page request.');
    if (/^(Network\.(getAllCookies|getCookies|setCookie|setCookies|deleteCookies|clearBrowserCookies)|Storage\.)/.test(method)) throw new Error('Browser account storage is not exposed.');
    return await this.api.debugger.sendCommand(this.source(sessionId),method,params);
  }
  static reason(error) {
    const text = String(error?.message || error || '');
    const kinds = [[/not attached|detached|disconnected/i,'not linked'],[/no tab with id|tab.*closed|target closed|no target/i,'tab closed'],
      [/cannot access|cannot attach|chrome:\/\/|chrome-extension:/i,'page Chrome guards'],[/another debugger|already attached/i,'another debugger'],
      [/context|frame/i,'page changed'],[/unknown browser tab|unknown tab|open a normal website/i,'tab not linked'],[/unsupported/i,'not allowed']];
    for (const [pattern,label] of kinds) if (pattern.test(text)) return ' (Reason: '+label+'.)';
    return '';
  }
  async detachAll() {
    const items = [...this.tabs.values()];this.tabs.clear();this.children.clear();this.aliases.clear();this.browserSessions.clear();
    await Promise.all(items.filter(t=>t.attached).map(t=>this.api.debugger.detach({tabId:t.tabId}).catch(()=>{})));
  }
}
globalThis.CompanionCDP = CompanionCDP;
