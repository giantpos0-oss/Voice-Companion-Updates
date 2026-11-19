"""Use the complete existing browser backend with an extension-owned tab."""
from web_assistant import BrowserBackend, WebError


NOT_LINKED = 'Your Chrome is not linked to Voice Companion right now. Check that Chrome is open, then try again.'


class ConnectedBrowserBackend(BrowserBackend):
    regular = True
    # Set by Companion: opens your Chrome, or waits for its extension to link again, and returns
    # True, words saying why not, or None. Before, a lost link was only ever waited on, saying "it
    # will reconnect automatically" when Chrome was closed (Will, November 18, 2026).
    relink = None

    def linked(self):
        """True once the extension is linked, reopening or relinking Chrome when it is not.
        Raises WebError with the reason when it cannot be linked."""
        if self.relay.connected.is_set():
            return True
        relink = type(self).relink
        result = None
        if relink is not None:
            try:
                result = relink()
            except Exception:
                result = None
        if self.relay.connected.is_set():
            return True
        raise WebError(result if isinstance(result, str) and result else NOT_LINKED)

    def __init__(self, folder, browser, relay):
        super().__init__(folder,relay.browser)
        self.relay = relay
        self.remote_browser = None
        self.target_ids = {}
        self.root_session = None
        self.generation = -1

    def start(self):
        self.linked()
        if self.page is not None and not self.page.is_closed():
            self.sync_active_tab();return
        self.close()
        from playwright.sync_api import sync_playwright
        try:
            import shared_playwright
            self.playwright = shared_playwright.start(self.folder)
            self.remote_browser = self.playwright.chromium.connect_over_cdp(self.relay.endpoint,timeout=15000,no_defaults=True)
            self.generation=self.relay.generation
            self.context = self.remote_browser.contexts[0]
            pages = self.context.pages
            if not pages:raise WebError('Open a normal website tab in your browser. It will link automatically.')
            self.page = pages[0]
            self.page.set_default_timeout(10000)
            self.root_session=self.remote_browser.new_browser_cdp_session()
            self.sync_active_tab()
        except WebError:
            # Its own reason ("Open a normal website tab") says what to do.
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise WebError('The browser link is not ready. Open a website tab and keep Companion open, then return to the Web browser menu.') from exc

    def sync_active_tab(self, _again=True):
        self.linked()
        if self.remote_browser and (self.generation!=self.relay.generation or not self.remote_browser.is_connected()):
            self.close();self.start();return True
        if not self.root_session or not self.context:return False
        target=self.root_session.send('VoiceCompanion.getActiveTarget').get('targetId')
        if not target:return False
        page=self._page_for(target)
        if page is not None:
            changed=self.page is not page
            self.page=page;self.page.set_default_timeout(10000)
            return changed
        # Your active tab is not one this connection knows: Chrome gave it a new target (opening a
        # link to another site can), or it opened after the connection. Keeping the old page made
        # every key wait 10 seconds for a tab that no longer answers (Will, November 18, 2026:
        # "it won't load a page"). The connection is made again, which finds every tab.
        if not _again:
            raise WebError('Companion could not find your active Chrome tab. Switch to that tab, then try again.')
        self._note('active tab not known to this connection, linking again')
        self.close();self.start()
        self.sync_active_tab(_again=False)
        return True

    def _page_for(self, target):
        for page in self.context.pages:
            if page not in self.target_ids:
                try:
                    session=self.context.new_cdp_session(page)
                    try:self.target_ids[page]=session.send('Target.getTargetInfo')['targetInfo']['targetId']
                    finally:session.detach()
                except Exception:
                    continue          # a tab closing while it is asked: not this one
            if self.target_ids[page]==target:
                return page
        return None

    def _note(self, text):
        try:
            from web_assistant import browser_note
            browser_note(self.folder, text)
        except Exception:
            pass

    def refocus(self):
        self.start()
        return super().refocus()

    def close(self):
        self.root_session=None;self.target_ids.clear()
        remote,driver = self.remote_browser,self.playwright
        self.page = self.context = self.playwright = self.remote_browser = None
        # Closing a CDP connection disconnects the driver; it must not close
        # the user's browser window or unrelated tabs.
        for action in (remote.close if remote else None,driver.stop if driver else None):
            if action:
                try:action()
                except Exception:pass
        if remote is not None:self.relay.client_closed.wait(2)


def create_backend(folder,browser):
    if browser=='webview2':
        from webview2_backend import WebView2Backend
        return WebView2Backend(folder)
    from browser_cdp_relay import current
    relay = current()
    return ConnectedBrowserBackend(folder,browser,relay) if relay is not None else BrowserBackend(folder,browser)
