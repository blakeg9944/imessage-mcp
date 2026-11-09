# Church guidance on using LCR member data outside Church tools

**This is research, not a ruling.** It summarizes public Church pages read on 2026-11-08 to give Blake a head start on the spec's step-10 check. Only the bishop (and the stake / Church Data Privacy Office, if needed) can say what is permitted. Page text changes, so re-read the linked sections before relying on them. Nothing here is legal advice.

## Bottom line

Church guidance never mentions texting members, personal spreadsheets, or personal Macs directly. But it points the same way on each point that matters. Membership data may be used only for approved Church purposes. It must not be exported from Church applications. It must not be stored or shared outside Church-provided applications, systems, or internet services. And sensitive information such as personal member data and confidential communications should not go into AI tools the Church doesn't provide or manage. Read plainly, a `contacts.csv` filled with LCR names and numbers, and member texts sent through Claude via Anthropic's API, are on the "not allowed" side of those rules. Using the data to schedule bishopric interviews is plainly an approved Church purpose, but that doesn't cure the export or AI-tool problems. Don't load real member data until the bishop has said yes in writing or in a clear message.

## Clearly NOT allowed (as written)

| Point | What the guidance says (paraphrase) | Source |
|---|---|---|
| Exporting from LCR | "Do not export membership or financial data from Church applications." | [Keeping Church Information Safe](https://www.churchofjesuschrist.org/tools/help/keeping-church-information-safe), section "Protecting Sensitive Information → Storing Data" (published 13 Aug 2026) |
| Consumer cloud storage | Don't store data from Church applications in consumer cloud apps such as Dropbox or Google Drive. | Same page, same section |
| Outside Church systems | Ward and stake leaders must not store or share confidential Church information outside Church-provided applications, systems, or internet services. Confidential examples include membership status and other non-public personal info. | [General Handbook 38.8.32 "Privacy of Members"](https://www.churchofjesuschrist.org/study/manual/general-handbook/38-church-policies-and-guidelines?lang=eng) |
| Cloud for membership data | The Data Privacy Office quotes Church Technology Standards saying cloud services for storing or backing up membership-related data are prohibited. | [Data Privacy Office](https://www.churchofjesuschrist.org/DataPrivacy), "For Church Leaders → cloud-based services" |
| Third-party AI | Sensitive information such as Church records, personal member data, or confidential communications should not be entered into AI tools not provided or managed by the Church. | [General Handbook 38.8.48 "Appropriate Use of Artificial Intelligence" → 38.8.48.3 "Callings and Assignments"](https://www.churchofjesuschrist.org/study/manual/general-handbook/38-church-policies-and-guidelines?lang=eng); announced in the [Dec 2025 Newsroom article](https://newsroom.churchofjesuschrist.org/article/general-handbook-enduring-guidance-artificial-intelligence) |
| Personal, commercial or political use | Member data may not be used for personal, commercial, or political purposes. Misuse should be reported and may need a membership council. | [GH 33.8](https://www.churchofjesuschrist.org/study/manual/general-handbook/33-records-and-reports?lang=eng) and 33.9.1; 38.8.32 |

Numbering caution: the Newsroom article cites the AI section as 38.8.47; the handbook text shows 38.8.48 (38.8.47 is "Travel Policies"). Some Church help pages cite "33.8.31" or "38.8.13" for privacy passages; in the handbook text the matching sections are 38.8.32 and 38.8.14. Navigate by heading.

## Clearly allowed

- **Using member contact info for Church work in your calling.** Access is granted by calling, and authorized users may use the information for purposes specific to that calling. Scheduling bishopric interviews fits. Source: [GH 33.1 and 33.8](https://www.churchofjesuschrist.org/study/manual/general-handbook/33-records-and-reports?lang=eng). Leaders must also respect each member's directory privacy setting ([GH 38.8.14 "Directories"](https://www.churchofjesuschrist.org/study/manual/general-handbook/38-church-policies-and-guidelines?lang=eng); [Digital Contact Information Visibility Settings](https://www.churchofjesuschrist.org/tools/help/digital-contact-information-visibility-settings)).
- **Viewing and handling data inside Church tools** under the protection rules: PIN or password on devices, don't leave devices unattended, encrypt and password-protect electronic copies where possible, lock up printouts ([GH 33.9.1](https://www.churchofjesuschrist.org/study/manual/general-handbook/33-records-and-reports?lang=eng); [Keeping Church Information Safe](https://www.churchofjesuschrist.org/tools/help/keeping-church-information-safe) "Mobile Devices").
- **Using Church-provided AI** (the handbook's wording implies Church-provided or Church-managed AI tools are the acceptable kind).

## Unclear (nothing found that settles it)

1. **A local file on a personal computer.** Pages ban consumer cloud storage, say not to export membership data from Church apps, and say not to keep membership info on *shared* computers. 38.8.32 bars storing it outside Church-provided systems. No page says "a personal spreadsheet on your own computer is fine" or "is banned" in so many words. The export rule and 38.8.32 make "no" the safer reading. Source of the gap: [GH 33.9.1.2](https://www.churchofjesuschrist.org/study/manual/general-handbook/33-records-and-reports?lang=eng).
2. **Texting members from a personal phone or Mac.** I found no Church page on leaders texting members or using group chats. The [Privacy Notice](https://www.churchofjesuschrist.org/services/platform/v4/resources/privacy-policy) section 3 only covers the Church's own SMS service. A bishop-approved calling-related website or social account is covered by [GH 38.8.21.2](https://www.churchofjesuschrist.org/study/manual/general-handbook/38-church-policies-and-guidelines?lang=eng), which requires bishop approval, but that is about web resources, not texting. Worth reading: [Use of Online Resources in Church Callings](https://www.churchofjesuschrist.org/pages/online-resources-for-church-callings?lang=eng) (linked from the Data Privacy page; **not read** in this pass).
3. **Whether a local-only tool counts as an "AI tool".** The AI rule targets entering personal member data into AI tools the Church doesn't manage. Claude via the API is clearly such a tool. A script that never sends data to a model is not an AI tool, but Blake's design does send names and replies to Claude.
4. **Replies as "confidential communications".** Texts from members about interviews may or may not count. Replies may reveal personal circumstances, which the handbook treats as confidential (e.g. 38.8.28.7 on not sharing personal information without permission).
5. **The Church Technology Standards** (quoted on the Data Privacy page) may be more specific. Not read: [Technology Standards](https://www.churchofjesuschrist.org/help/support/meetinghouse-technology/my-calling-as-a-technology-specialist/technology-standards?lang=eng).

## Retention and deletion

- Keep records only as long as needed for administrative, legal, and historical purposes. Outdated records must be destroyed so they can't be retrieved or reconstructed. [GH 33.9.2 and 33.9.3](https://www.churchofjesuschrist.org/study/manual/general-handbook/33-records-and-reports?lang=eng); [Retention of Records](https://www.churchofjesuschrist.org/tools/help/retention-of-records?lang=eng) (published 7 Apr 2023).
- Printed copies of membership records: destroy as soon as a member moves out of the unit.
- No page gives a retention period for member phone numbers or message logs specifically. Treat the send log and replies as Church records under the general rule.
- Questions go to the Data Privacy Officer: DataPrivacyOfficer@ChurchofJesusChrist.org (per GH 33.9.1.3).

## What this implies for Blake's setup

- **`contacts.csv` on his Mac.** This is the most likely problem: it is an export of LCR membership data to a personal device. Under the export rule and 38.8.32, assume not OK until the bishop says otherwise. If the bishop approves, he should also decide on: FileVault on, strong login, no iCloud Drive / Dropbox / Google Drive syncing of the file or repo folder (including Time Machine to cloud, if applicable), minimal columns (name, number), deletion when no longer needed.
- **Local send log.** Same category: member names, numbers and interview scheduling are membership-related records. Same storage and retention caveats. Keep it minimal and delete on a schedule.
- **Member texts through Claude.** This is the clearest conflict with 38.8.48.3: personal member data and member replies would go to a non-Church AI service. Options to raise with the bishop: don't send real names or numbers to the model (use IDs or first names only and map locally), keep Claude out of the reply-reading path, or don't use the AI part at all and keep the tool as a local script.
- **Safe interim:** the demo / dry-run mode with fake data, which the repo already has, doesn't touch any of this.

## Who should settle it

1. **The bishop**, because he directs the ward's use of member data and approves ward resources (cf. 38.8.21.2). Ask him specifically about: (a) a local contacts file made from LCR data, (b) texting members from Blake's own phone or Mac, (c) member info and replies going to a third-party AI service.
2. **The ward clerk** (keeper of membership records) for how LCR data is meant to be used and whether the ward's own contact process already covers texting.
3. **The stake technology specialist or stake presidency**, if the bishop is unsure.
4. **Church Data Privacy Office:** DataPrivacyOfficer@ChurchofJesusChrist.org, for a written answer.

## Method and limits

- Read: GH ch. 33 and 38 (ch. 38 read in pieces; 38.8.1–38.8.13 not read verbatim), Keeping Church Information Safe, Retention of Records, Digital Contact Information Visibility Settings, Privacy Notice, Data Privacy Office page, and the Dec 2025 Newsroom AI article. All are official Church pages.
- Could not read: the Church records "protection" page (redirects to a host that wouldn't resolve). Not read: Technology Standards, Use of Online Resources in Church Callings, Text and Messaging Terms, the Church's AI page.
- Forum posts on tech.churchofjesuschrist.org appeared in search results; those are member-written and were not relied on.
- The Privacy Notice is dated 2021-04-06 and is about the Church's own processing, so it says little about leaders' personal tools.
