# Daily sweep log

Every bug fix and design question from the nightly sweeps, newest first. Will reads
this, or asks for it, instead of getting a message each night.

The format for each night:
- a heading with the date and the version
- under it, a "Fixed" list and a "Questions for Will" list

## November 6, 2026 (night 6, keyboard only): version 0.2.208-test

Release pull request 140. Try pull request 139 ran the new real-window tests on Windows.

### Fixed

#### Startup and main menu
- F1 opens Help in Office tools and in Shut down or restart.
- Alt+O opens Options from Office tools, Shut down or restart, and the Media menu, and comes back to that menu.
- No or Escape at "Restart the computer?" goes back to Shut down or restart, not the main menu.
- The email account question (no account set up) was cut off by "Main menu". Fixed.
- "Main menu" or Control+F1 at the account question now cancels it. Before, the arrows still moved through account types.
- Control+T, F1, Help, waking up and Alt at the account question now handle it the right way.
- Enter before choosing an account type tells keyboard users to press T or Y.
- The main menu no longer sends you into Office tools after Help or Options.
- Guide 1.3 and 26.3 updated for Shut down or restart.

#### Questions on every screen
- F1 now reaches the app during a Yes or No question in the real window. Calendar and Contacts say the question again and keep the choice.
- Closing Help in Calendar or Contacts says the list or question still open.

#### Email
- Escape in the To, CC, BCC or Subject box keeps the typed text and asks the leave question.
- Control+R, Control+Z and Control+Y work in the CC and BCC boxes.
- Subjects that start like a command ("Save the date", "Help with the move") stay the subject.
- Delete in an open message asks to delete it, as the guide says.
- Keys no longer change the message while the send review asks Y or N.
- Attachments list: Delete and attaching another file keep the other tags. The Alt menu has a Tags group.
- An empty folder says the same words for C, E and H as for other keys.
- Leaving a never-sent draft no longer warns about sending twice.
- Control+F1 in the attachments list says only the main menu.
- Guide 10.3: Add contact is Alt, 5, then 5. A test checks every email Alt path in the guide.
- Test isolation: the drafts list no longer leaks between test files.

#### Calendar and Contacts
- A new contact canceled with Escape leaves nothing open.

#### Files and documents
- Y and N answer File manager's Delete question. F1 says it again.
- Typing "help" in a box is text. Saying "Help" while renaming gives help instead of renaming the file.
- File keys close Properties first.
- One Escape after one typed letter goes back.
- Alt, Go to, Main menu works.
- A used name keeps the rename box open.
- Delete and rename say what they did.
- Each box says what to type when Enter is pressed empty. Each Escape says what was canceled.
- Search says "1 match" and "No matches".
- Control+Shift+F in the drive list says to open a drive first, at once.
- Sixteen document menu items say in plain words what to type.
- No more double periods in menu items.

#### Web
- Shift with a number 1 to 6 goes back to a heading at that level.
- The flaky live test is fixed: after a page stayed open for unsaved changes, Chromium could stop the next page change at once. Companion now tries once more in that case.
- Escape in a form question stays on the page.
- The fields list (F8) says its keys once, then only each field.
- The page menu shows Control+Home and Control+End.

#### Media and the window
- Alt+T keeps letters and spaces on every screen. Escape clears a typed command.
- Space in a list menu says to press Enter, and no longer blocks the arrows.
- Radio and Podcasts forms: Space presses OK or Cancel; other keys say what to do.
- An empty preset list no longer opens Station actions.
- Escape from results says "Radio menu" or "Podcasts menu" first.
- After removing an item, the list stays near it and says where you are.
- F5 in Radio uses plain words, and "1 station".
- Media player says "Loudest" and "The audio is silent" at the volume ends.
- End and Page keys in the YouTube player say which keys to use.
- Escape from the Media player drive list lands on Media player. Guide 19.1 corrected.

### Open items for the next sweep
- Published as 0.2.208-test. The new window tests passed on Windows (try pull request 139). The email and calendar ones ran in the release. Add test_keyboard_documents_sweep.FileBoxWindowTests and the three test_media_form_window classes to the window test list in the next release, and take test_media_form_window out of NOT_IN_BUILD in tools/test_release_list.py.
- test_keyboard_text WindowKeyboardTests test_file_tab_stays_in_the_list_and_new_file_keys_reach_the_app fails on Linux at the Control+Shift+3 key code, on main too.
- Thunderbird add-on delete inside Trash with messages.delete(ids, false) is still open.
- The scratchpad is shared by all helpers. Give each helper its own subfolder.

### Questions for Will (not answered yet)

#### Startup and menus
- Should the main menu remember your place after Escape from Office tools, Media or Help?
- Should Control+F12 at a Yes or No question say "Answer the question first"?
- Should Escape from the tutorial lesson list go back to the lesson you were on?

#### Email
- While the inbox asks a question, should F5, Space, Delete and the Page keys be blocked too?
- In the attachments list, should Delete act on every tagged file, as in File manager?
- Should Escape from the folder and drafts lists say where you are?

#### Calendar and Contacts
- Should a key (for example Control+L) change the calendar for a new event?
- Should Escape at any step keep a half-made event or contact?
- Should End go to the last event of the day?
- Should letters jump in the list of what to change?

#### Documents
- Should Control+S in a note stay in the note, as in a document?
- Should Escape clear a File manager search before going up a folder?
- Should Tab, Page Up and Page Down in File manager say they do nothing?
- Should Escape at the Save As folder step go back to the name step?

#### Web
- After arrows change a choice box, should Escape put back the old choice?
- Should Delete in the favorites and history lists ask to delete?
- Should the form question prompt mention typing and Escape?

#### Media
- Should Control+O while a file plays stop the audio, as leaving the player does?
- After Stop, should What's playing say "Stopped" instead of "Paused"?

## November 4, 2026 (night 5, empty and edge states): version 0.2.203-test

Release pull request 132. Night count: sweeps since November 1 run Monday, Wednesday and Friday, so tonight is sweep night 5 (November 2 was night 4; it left no log entry). No new Windows-only tests, so no try branch.

### Fixed

#### Startup, speech and Help
- After Pause, the main Windows voice stayed silent: a stop threw away the waiting Resume. Stop now drops only waiting speech.
- One failed voice restart left no voice for the rest of the session. It now tries again on the next call.
- A damaged speech-settings.json (a list, null, text or a byte order mark) stopped startup. It now uses no saved settings.
- F1 was silent in the update question with the microphone off ("Press Y or N"). At startup, F1 repeated the whole announcement instead of the question.
- Guide part 29.5 asked for a permission for online recognition, which was removed in 0.2.201. Line removed.
- "Help with e-mail." and chapter names without commas found no topic. "Help, please." now works on the main menu.
- The transcript lost every line when speech-transcript-old.txt was held open. It now keeps writing and moves the file later. The Thunderbird log gets the same fix.
- Options are saved with the shared atomic writer (it now flushes to disk and leaves no preferences.writing).

#### Email
- Picture-only emails (HTML with no words) said "No readable body." Yahoo and Thunderbird now read the plain part.
- "From: <>" was read as symbols. Now "Unknown sender."
- Message numbers in an empty folder said "That number is not on this page." Now "Empty list."
- A save cut short left "Name.writing" in the drafts list.
- Accented letters in messages with no character set were garbled. Now UTF-8 first, then Windows Western.
- A removed account now adds "Say add account to connect it."
- Replies and forwards to a blank subject were sent as "Re: (no subject)." Now "Re:" or "Fwd:".
- A damaged preferences.json stopped every inbox command. Email now uses one shared reader.
- "undisclosed-recipients:;" was read with its symbols on Thunderbird. Now "No To address."

#### Calendar and Contacts
- A removed calendar or address book was named "All calendars" after Refresh.
- Contacts saved on this computer: a damaged file was written over by the next contact; a file with a byte order mark read as empty; a held file was replaced. All fixed, with a .damaged.json copy kept.
- Deleting the last contact on "Saved on this computer" jumped to every address book.
- February 30, and February 29 in a non-leap year, put the event on the day on screen. Now it names the problem and asks again, for add and move.
- "What's on my calendar for February 30?" was not understood. Now it says why.
- Adding an event with no calendar to save in opened Calendar without a word. It now stays on the main menu and says why.
- Control+L with no calendars or no address books spoke of one email account.
- "Email John" with no John read the command list. Now "No contact named john."
- Enter and Delete on an event past midnight said "tomorrow" for a day that is not today. Now "the next day."

#### Documents, notes and files
- Extend selection, Select to end of line, Select to the end and Select to the beginning did not work in documents and drafts. The editor now uses the shared selection rules.
- Selecting nothing said "Selected:" and Delete added an empty Undo step.
- Drafts said "Beginning of document" and "The document is empty."
- A paragraph of only spaces was silent. Now "Empty paragraph."
- Damaged Word files read out Python errors, or stopped the command.
- A damaged Word file from Open a document lost the file list place.
- "Read a document aloud when it opens," turned off, was ignored for text and PDF files.
- Select previous paragraph, word and sentence skipped one on a blank line.
- Empty note selection said "This field is empty."
- File manager: Delete and Rename now keep focus in place. "Name tags.txt" is no longer cut to "tags.txt."

#### Web
- A page dialog with no buttons trapped Escape. The message now says if it has a button, and a second Escape opens the web browser menu.
- Arrows in an empty table said "Move to a table with T first." Now "This table is empty."
- A download folder at the top of a drive was named as nothing. Now "drive E."
- Your own Chrome, hidden while Companion used it, stayed hidden after Companion closed. It now comes back.
- Main menu during Chrome setup gave a shorter message than Cancel.
- Review form on a page with no fields said only "End of form review."
- Submit form offered a disabled button, then said the result was uncertain.
- The flaky test test_unsaved_changes_keep_the_page_and_a_second_try_leaves could not be made to fail here (8 alone, 10 under load, 2 full live runs). It now records each step, its timing and the page, and prints that record on failure.

#### Media
- Seek and chapter keys with nothing loaded said the audio cannot seek or has no chapters.
- Playback speed with no media file asked for a number first.
- Play or delete preset with no presets said "I could not find that preset."
- Empty subscriptions, downloads and recordings now say what to do next.
- Download with no episode open gave the general Podcasts help.
- "Play station 9" with 3 results gave a raw error. Now it gives the range. Same for Record and Schedule.
- Radio Recordings listed desktop.ini and Thumbs.db, and said ".mp3" aloud.
- A damaged automatic download setting was read raw and stopped the background feed check.
- Subscribing twice said "Subscribed" again.
- Space was silent in Yes or No questions on Radio and Podcasts.
- Player controls' Escape hint named the menu instead of the list Escape goes to.
- Scheduling for 12 AM today at night now explains that midnight tonight is 12 AM tomorrow.
- With no internet, radio search and "Play WGN" now say to check the connection.

#### Found while merging
- The new web Escape test failed only in the full run, because an earlier test left a spoken list open. The test now clears that state first.

#### Found while shipping
- The first Windows build failed: the new transcript test left its file open, and Windows cannot delete an open file when the temporary folder is removed. The test now closes the transcript first. The second build passed, and 0.2.203-test was published.

### Open items for the next sweep
- Keyboard voice (keyboard_speech.py) still calls the Windows voice directly, with the same freeze risk 0.2.196 fixed for the main voice.
- If the Windows voice takes more than 5 seconds to start, the chosen voice is not applied, and the next save can write the default over it.
- Thunderbird add-on: delete uses messages.delete(ids, false). On an IMAP account set to "Remove it immediately" this may delete for good. A fix would move to the account's Trash folder. It needs a try branch with real Thunderbird. From Thunderbird 137 the second argument is an options object.
- The Document reader shows "This document has no readable text." as the text of an empty file, so Copy can copy it.

### Questions for Will (not answered yet)

#### Startup and Help
- Should "Wake up" said while awake say "I am awake"?
- Should a setting name said alone ("Verbosity", "Rate") say the current value and choices?
- In the tutorial, should "Where am I?" say where you are in the tutorial?
- Should a bare "Explain command" ask which command?
- Should Page Up and Page Down move by a page on the main menu, Help and tutorial lists, or say they do nothing?

#### Email
- Should the message list say the address when a sender has no name?
- On a forward or a reply with no address, should a sentence said in the To field go into the message?
- Should a reply go to every Reply-To address?
- Should a damaged draft offer to open its last good backup copy?

#### Calendar and Contacts
- Should the day's list say "the next day" for events past midnight, as Enter and Delete now do?
- Should the Thunderbird add-on move deleted mail to Trash itself, so it never deletes for good?
- "Go to the 31st" in a 30-day month goes to next month's 31st. Should it say the month has no 31st?

#### Documents
- Should an empty file open in the Document reader with no text at all?
- Should a Word file too large for the editor open in the Document reader by itself?
- Should "Go to beginning of message" and "Go to end of message" be commands in a draft?
- Should "Select letter" work in documents?

#### Web
- Is a second Escape on a stuck dialog opening the web browser menu the right way out?
- Should Tab on an empty page and the first reading use the same words?
- After an empty Enter in the search box with a page open, should the search box stay open?

#### Media
- Should YouTube in your own Chrome only reuse tabs Companion opened?
- While one show plays and you browse another, should "Next episode" go to the next episode of the show that is playing?

## October 31, 2026 (night 3, a code review of error handling): version 0.2.189-test

Release pull request 111. No new Windows-only tests, so no try branch. All three checks were green at 10:07 AM UTC. This session's permission check blocked the merge, so Will merged it himself. It was published at 4:05 PM UTC.

### Fixed

#### Startup, Options, sleep and updates
- A damaged update settings file in the data folder no longer stops startup; it uses the feed that came with the app.
- A full disk while copying the user guides no longer stops startup or the installer's guide refresh.
- Damaged saved options are copied to preferences-damaged.json and said once at startup.
- Reading the update helper's ready file while it is still empty no longer says "The update could not start."
- Yes to an update from a note that cannot be saved waits, and keeps the note.
- Alt+O opens with a damaged podcast, radio or AI voice file.
- A failed Options save says it in plain words, not an error number and a path.
- Spoken setting changes (speed, volume, verbosity, punctuation, modes, voice, capitals, Start with Windows, web reading choices) still work when the file cannot be saved, and say so. F9 and the transcript switch say so too.
- Restart and Shut down keep a note that cannot be saved, and name a failing draft.
- A missing, damaged or empty guide no longer stops Help or the tutorial.
- Going to sleep with a draft or note that cannot be saved keeps the words and says so in one message.

#### Email
- New email, send, file manager, another account and reply no longer stop the app when the draft cannot be saved.
- A move or delete that stops halfway clears the open message and says to list the folder again.
- Yahoo reads flagged, answered and forwarded.
- Thunderbird's add-on update restarts Thunderbird only once when its file is in use (also found by the Calendar helper; merged into one fix).
- A damaged or locked draft says what is wrong.
- After a folder change, the Inbox is listed again.

#### Calendar and Contacts
- A slow Thunderbird is its own error ("did not answer in time"), not "not connected"; a slow change says to check before trying again.
- A Thunderbird that will not close for the add-on update says nothing changed.
- A failed read keeps the chosen address book; Control+L says what went wrong.
- A failed delete says nothing was deleted and what to try.
- A damaged answer from Thunderbird no longer stops Contacts or Calendar.
- "Email John Smith" uses the last contact list when Thunderbird is slow.

#### Documents and files
- Changes to a document open in Word or on a full disk stay in the document, say so, and no longer stop the app (new editor_process helper).
- Undo with a locked file no longer drops the step.
- A document save is flushed to the disk before it replaces the old file.
- Old documents are copied once, so deleted or renamed documents no longer come back.
- The Recent documents list is written atomically; write_text_atomic removes its temporary file on failure.
- Typing-window edits that would join or split table cells are refused with a plain message.

#### Web
- A garbled favorites or history file no longer stops the browser; a file with a byte order mark is read.
- Saving, renaming or deleting a favorite while the file is held says nothing changed.
- Download history is no longer written over after a failed read.
- Load failures say the real reason (no internet, no such site, too slow, no answer, security check).
- Keys and commands say the real browser link reason instead of "it will reconnect".
- Resume no longer blames a favorite.
- Change Address in form review no longer stops the app.
- An unexpected error in a spoken web command says to press F5 and try again, and records where in web-command-error.txt (no page text).
- No more empty names or doubled periods in web speech; "[example.com" no longer says "Invalid IPv6 URL".
- The extension popup no longer stays on "Checking" forever (extension 0.4.4; testers choose Reload).

#### Media and the window
- Broken or cut-off station and feed replies (HTTPException) no longer stop the app.
- Failed SHOUTcast recordings and cut-off podcast downloads say so; part files are removed.
- Bad station directory replies and damaged IPRD catalogs are skipped.
- Radio and Podcasts keys handle errors as voice does.
- Media errors are said in plain words (new spoken_error).
- Recording folder and disk errors are named as disk errors, and do not hide the station.
- Next and Previous chapter say the player could not respond when its browser closed.
- Damaged podcast subscriptions are skipped.
- The Media player screen says the player did not answer instead of stopping the app.
- A scheduled recording with no web address is reported as damaged.
- Counts: "1 new episode", not "1 new episodes".
- The window's update loop keeps a bounded error list and no longer floods the log.

### Questions for Will (not answered yet)

#### General
- There is no catch-all around commands: any unexpected error closes the app with "Voice Companion stopped because of a problem." Should every screen get a plain safety net, as the web commands now have?

#### Email
- A subject such as "High priority" is taken as the importance command. Should the Subject box keep it as the subject?
- The general mail error names the account even when the account is not the cause. Change the wording?

#### Calendar and Contacts
- A dropped connection retries a request once, so an add could make a second copy. Should changes skip the retry?
- Calendar says "No events." before the reason when it could not be read. Should it match "What's on my calendar"?
- Should a failed new event keep the time and name already given?

#### Documents
- Changing only the capitals of a document name says the name already exists. Allow case-only renames?
- The editor says "empty or damaged" and the reader "damaged or empty"; neither says what to do next. Reword?
- Email drafts are saved without being flushed to the disk first. Flush them like documents?

#### Web
- Allow international site names such as münchen.de?
- Keep "End of list" before "No next heading"?
- Tab on an empty page gives two messages. Intended?

#### Media
- Should media screens catch every error and say something plain, not only known error types?

## October 30, 2026 (night 2, an expert screen reader user): version 0.2.181-test

Release pull request 99. Try run for new Windows-only window tests: pull request 98.

### Fixed

#### Startup, sleep, Help and the tutorial
- Waking at the Exit, Restart or Shut down question asks it again, not "Back to exit confirm."
- Sleep with the microphone off says to press Control+F12 to wake; waking leaves out "I am listening." The tutorial uses the same words.
- "Canceled." is joined to the next message, so it is heard.
- Control+F1 or "Main menu" in Help says "Help closed."
- An update offer answered No while asleep goes back to the screen you slept on.
- The transcript notice at startup says to wake Companion first, or how to turn it off with no microphone.
- Mode phrases, "What mode?", "What version?" and "Where am I?" work in Help.
- Moving in Help and the tutorial says only the item; the hint is said once.
- The tutorial names all 12 courses; the guide names YouTube.
- "Switch to normal mode / commands only / dictation only" and "What mode am I in?" forms work.
- A test that relied on leftover sleep state now sets its own (passed alone, failed in the full run).

#### Email
- One period after a subject; a blank subject says "No subject".
- Escape from Attachments says the message you are on.
- Canceling a reply or new email goes back to the message or your place in the same folder.
- Closing a saved draft says it is still saved.
- Delete in Thunderbird Trash and Yahoo Trash says nothing changed before asking.
- Moving a message to its own folder says nothing changed.
- Marking wording is the same by key and by voice.
- An empty folder gives one message to every key.
- Spoken numbers up to one hundred work ("read message fifteen").
- "What folder am I in?" and "Go to the message list" work.

#### Calendar and Contacts
- An event or contact removed elsewhere leaves the list; the day or list is read again.
- "Where am I?" and "Repeat" keep your place; both screens know next item, previous item, top and bottom of list.
- Y and N no longer close the Calendar change list or calendar list.
- "Schedule lunch with Bob tomorrow at noon" and "Add dinner Friday at 6 PM" add the event on Calendar.
- "What's on my calendar today?" from another screen names a calendar that failed.
- "Email John" says Thunderbird's reason when contacts cannot be read.

#### Documents and files
- Reading a paragraph, line or word no longer moves your place; delete word and sentence act on the current one.
- Deleting or cutting a word or sentence leaves no extra spaces.
- No doubled periods in Cut, Deleted, Pasted, Replaced and Insert messages, or reader notes.
- Formatting is said in plain words (Italic, Heading 2, Font Arial).
- "Make it quick." and similar are written; only "make it" plus a number sets the size.
- Redo goes to the paragraph it changes; delete paragraph starts at the next paragraph.
- Reader Find drops the period speech adds; Find with no words asks for them.
- Save As suggests Documents when Desktop is missing.
- File manager says "1 item"; "What is selected" works.

#### Web
- Tab and F reach tabs, switches and spin buttons; Enter selects a tab, toggles a switch, or lets arrows change a spin button.
- Role words are the same on the page line and with quick keys ("spin button", "progress bar"; switches say on or off).
- Unlabeled controls no longer say their type twice.
- "Top of page." and "Bottom of page." at the ends.
- Fields say their value, "invalid entry", and the site's hint; passwords are never spoken.
- Saving a favorite by voice never replaces another favorite (lost data).
- "List form fields" and similar open the fields list.
- T says a table's rows and columns.

#### Media
- YouTube Page Down and Page Up reach the screen in the real window.
- Space and other player keys on the controls list keep your place.
- Keys in an empty Radio or Podcasts list say the list is empty.
- YouTube Down at the end says why the next part did not load; fewer repeat requests.
- End in the Media player says how to reach the player menu.
- A slow-starting podcast episode still opens the player controls.
- "browse feeds" is now "browse podcasts".

#### Found while shipping
- A release-note sentence was over the reading level.
- Two new Help tests expected 32 topics; Windows has 33 because What's new is built there. They now count the topics.

### Open items for the next sweep
- test_web_media_live LiveDialogTests.test_unsaved_changes_keep_the_page_and_a_second_try_leaves is still flaky (failed once on main's side tonight). Make it report which step failed and how long each took.
- Many test files set companion.SLEEP_RETURN_MODE and never restore it.
- Stopped run_checks runs leave /tmp/vc-compare-* worktrees behind.
- Helpers should each get their own scratch subfolder.
- tools/helper-rules.md has an old Claude-Session footer.

### Questions for Will (not answered yet)

#### Startup and Help
- Should Control+F12 in a Yes or No question do what "Go to sleep" does?
- Should Verbosity Low also shorten list hints?
- Should "Update status" and "Cancel update" with no update say "No update is downloading."?
- "What version?" mid-session says "The microphone is off, as you left it." Keep that?

#### Email
- Should "Back to inbox" from a reply go to the Inbox list, not the message?
- Name new drafts by subject instead of "Untitled 2"?
- Folder list wording differs between the first item and the rest.
- Rename folder lists standard folders that cannot be renamed.
- Reply to a message with no subject sends "Re: (no subject)".
- Drafts list Escape says only "List closed."; "Where am I" in a draft does not say "Email draft".
- The Delete question says "Trash or Deleted Items" instead of the real folder.
- From the main menu, "Email John", Escape, then "yes" saves the draft and opens the Inbox.

#### Calendar
- Should End go to the day's last event?
- A week summary ("What's on my calendar next week?") would be a new feature.

#### Documents
- Control+S in a note goes to the main menu; in a document it keeps you writing.
- No way to delete a saved note.
- "Recent documents" works only in the Word processor menu.
- The reader has no "spell word" or "where am I"; its Find wording differs from the editor's.
- Renaming a document leaves its old backup file behind.

#### Web
- Tab past the last control: stay put, or wrap like a browser?
- Heading list says "Chapter 2 2" for a level-2 heading named Chapter 2.
- One word for each role: "edit" or "edit field", "combo box" or "choice box"?
- Should Control+F jump to page text before matching links and buttons?
- Add lists for landmarks, buttons and tables?

#### Media
- Should "Where am I?" and "Repeat" work on Radio, Podcasts and the Media player?
- After Stop, should "What's playing?" say "Stopped"?
- Page Down and Page Up on Radio and Podcasts?
- Should Enter on a station open the player controls, as on Podcasts?
- Key presses still read spoken-command hints.
- Podcasts skip 15 seconds by key but the controls list says 30.
- A wording pass to replace "feed" in podcast messages.

## October 29, 2026 (night 1, a new veteran): version 0.2.175-test

Release pull request 81. All three checks passed. The session could not merge it, so Will merged it; 0.2.175-test was published on October 29.

### Fixed

#### Startup, Help and the tutorial
- "What mode?", Control+M and Options say Normal mode, Commands only and Dictation only, as the guide does.
- Typing "Wake up" goes back to the screen you were on.
- Sleeping during a Yes or No question (save, replace, name) asks it again on wake.
- "Help with" an unknown topic says so and reads the topic list.
- "Help with" finds main menu, keys, microphone, time, yes or no, lessons, voices, exit, transcript; ignores "the" and "my".
- "Start the tutorial", "Open the tutorial", "Start lessons" start the tutorial.
- "What version is this?" and similar say the version; "Version." in a document is text.
- F9 with a microphone that cannot start no longer says voice commands are on.
- Startup message says to wake Companion before saying start tutorial.
- Long tutorial lessons split in better places.
- Guide no longer says "Pause" silences Companion.

#### Email
- Hide Thunderbird no longer starts a closed Thunderbird.
- Changing the address no longer sends the next sentence into the subject.
- Reply subject says how to get back to the body; "Subject is…" in a reply body is written.
- Spoken subject drops the extra period.
- Inbox understands everyday words: go to the trash, open the first message, read the next message, close message, check my email, refresh.
- Unknown inbox words start with "I did not understand that."
- Clearer message for Reply from the list; plural wording fixed.
- Escape cancels the add-account question on every screen; Next, Previous and That one work there.
- After delete or move you land on the next message.
- A draft written before an account existed can be sent.
- "All messages" wording tells how to reach more mail.
- Yahoo: deleting inside Trash says nothing changed.

#### Calendar and Contacts
- "Make an appointment for Friday at 10 AM" asks for the name instead of naming it "for".
- Evening, afternoon and "at night" set the time and stay out of the name; "Friday evening" then "7" is 7 PM.
- "Schedule a doctor appointment…" and "Add a reminder…" work.
- "No" as an event or contact name asks again; "No" to a contact's email skips it.
- "Delete it", "remove it", "cancel my appointment" work.
- "Add a new contact", "go to contacts", "phone book", "my schedule", "my appointments" work.
- "Show my Outlook calendar" from the main menu: one message, Calendar first.
- "Where am I?" on Calendar says Calendar.
- Thunderbird save failures say what to do next.
- Phone-only contact is "No name"; "Saved on this computer" wording; repeating-event question wording.
- Freeze report written atomically (a test that passed on rerun; cause fixed, noted in LAUNCH-CHECKLIST).

#### Documents, notes and files
- Leaving a document Word has open no longer stops the app.
- Enter, Home and End work in List documents and the Notes list.
- Failed saves no longer leave .writing.docx or .restore.docx files.
- "Open document" a complex Word file opens it in the Document reader; damaged files named plainly.
- Escape from Open a document inside a document goes back to the document.
- Copy and Cut after Select all copy or cut.
- File manager rename accepts "dot" and a trailing spoken period.
- "dot docx" spoken at the end of a name is not added twice.
- End and beginning of document, note and email are announced.
- Reader "Go to end of document" goes to the very end.
- Empty-folder keys in File manager say the folder is empty.
- Resume document with none open stays put; deleting a blank paragraph says so.

#### Web
- Upload buttons with Chrome in the background explain how to show the window.
- "Show browser window" with your own browser says to use Alt+Tab.
- Show browser window on a page that failed to open no longer misleads.
- Spoken addresses ("v a dot gov", "w w w dot…", "V.A. dot gov") offer to open the site.
- No stray "., " before item types.
- "List links" on a page without links says "No links on this page."
- Favorites and web history are never wiped by a locked or damaged file.
- Sign-in security codes and ID expiration dates are not taken for card payments.
- Site cookies carried over when Chrome restarts.
- Fill out this form: Skip, Cancel form, "Yes, please", "Oregon." work.
- List favorites on the main menu opens a real list; web history and favorite commands on the main menu open the web browser menu.
- A card or file box appearing on a page in use no longer restarts Chrome and loses typing.

#### Media and the window
- "Play" plays the chosen station, preset, episode or YouTube video.
- YouTube Stop and Resume control a loaded video.
- "What's playing?" on YouTube with nothing playing says how to start a video.
- Damaged radio files read as empty; damaged schedule and subscriptions kept and reported.
- Preset and station names keep capitals.
- Scheduled recordings list says day and time in words.
- Correct wording for Pause radio during a media file, Delete on results, Tab during playback.
- "Play the radio" and "Play it again" no longer search for "the" or "it".
- "Open radio", "Listen to the radio", "Podcast.", "Open podcasts", "What video is this?" work.
- Command box keeps its room at 400 percent text on small screens; Tab never moves focus silently (passed twice on Windows, draft PR 80).

### Open items for the next sweep
- test_web_media_live LiveDialogTests.test_unsaved_changes_keep_the_page_and_a_second_try_leaves fails on main sometimes and passes other times. Find the cause.
- Thunderbird add-on deletes inside Trash with messages.delete(ids, false); may delete for good. Check on Windows.

### Questions for Will (not answered yet)
- Should "Pause" also silence Companion's speech when nothing is playing?
- In a Yes or No question, should F1 say the question again?
- Should "Text size 1000" say the allowed range?
- Should the main menu understand "Help me", "What can I say?" and "Go back"?
- In a new email's body, should "Subject is …" be written as text instead of changing the subject?
- In the inbox, "Open email" reopens the inbox from scratch. Should it open the current message?
- Some send words ("send my email", "send now") are written as text. Should they send?
- Should "Next Tuesday" said on a Monday mean tomorrow or a week later?
- Should "half past two" and "quarter to three" be understood as times?
- Should Undo work in notes, and should "Scratch that" in a note remove the last dictation?
- Should a spoken rename keep the old file type?
- Should recent lists drop files that are gone?
- After Escape in a web text box, later sentences can be typed into the page. Should that stop?
- On a web page, one word like "page" can match a link. Should matching be stricter?
- Should "Go back" leave Radio results at the first station?
- Should "Skip" on YouTube mean "Skip ad" when an ad shows?
