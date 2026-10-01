# Job Scout

Job Scout finds job openings for one job seeker every day, scores them against the job seeker's profile, and sends the best ones to Telegram for triage. It never applies for jobs or contacts anyone.

## Language

### People

**Job seeker**:
The one person a Job Scout instance works for. In this repo that is Rahat; in a forked template it is whoever imported it.
_Avoid_: User, candidate, owner

**Suggested contact**:
A person at a lead's company whom Job Scout suggests the job seeker reach out to, with a reason. Job Scout never contacts them. For a lead that came from a hiring post, the post's author is the first candidate. A lead's suggested contacts are found once and reused.
_Avoid_: Contact, referral target, outreach target, lead

**Referral**:
The job seeker has someone at a company willing to refer them. It is a flag on the company, set from any of its leads, and applies to all its current and future leads.
_Avoid_: Referrer, intro

### Finding openings

**Board**:
One company's public job board on an ATS (Ashby, Greenhouse or Lever), identified by the ATS and the board name.
_Avoid_: ATS (the vendor, not the board), job site, careers page

**Posting**:
One job's page on a board, identified by the board and the ATS job ID.
_Avoid_: Listing, job ad

**Hiring post**:
A post on X that announces an opening.
_Avoid_: Tweet, job tweet

**Source**:
Where Job Scout found a lead: a board or X.
_Avoid_: Channel, feed

**Scan**:
The scheduled daily search across all sources that creates new leads.
_Avoid_: Run, crawl, search job

**Lead**:
One job opening Job Scout tracks, found in a scan. A lead is identified by its posting. A hiring post that links to a posting belongs to that posting's lead. A hiring post with no posting link is its own lead, identified by the post.
_Avoid_: Job, role, opportunity, listing

**X-only lead**:
A lead that comes from a hiring post with no posting link. It becomes a lead only if it is judged to be a real opening.
_Avoid_: Tweet lead

### Scoring

**Profile summary**:
A few lines describing the job seeker's roles, stack and goals. Leads are scored against it instead of a full resume.
_Avoid_: Resume, bio

**Role family**:
A group of job titles the job seeker targets, such as DevRel/DevEx or Product/Frontend Engineering.
_Avoid_: Category, track, bucket

**Sub-score**:
One scored dimension of fit: role family, stack, seniority, location, domain, freshness or referral.
_Avoid_: Signal, factor

**Fit score**:
A lead's total out of 100: the sub-scores combined with the weights in the config.
_Avoid_: Match score, rating, rank

**Filtered lead**:
A lead that failed a hard rule (location, pay floor or excluded title) before scoring. It is kept with the rule it failed and is never sent. Unknown pay or location never fails a rule; only a stated value that breaks it does.
_Avoid_: Rejected, dropped

**Minimum fit score**:
The fit score a lead needs to be sent at all. Default 60.
_Avoid_: Threshold

**Unscored lead**:
A lead whose scoring failed during a scan. It is scored again on the next scan and is never sent until it has a fit score.

**Freshness window**:
How long after Job Scout first sees a lead it can still be sent. Default 30 days. Separately, the freshness sub-score decays as the posting ages (from the earlier of its publish date and first sighting) over the same number of days, so an old posting found today can still be sent but ranks lower.
_Avoid_: Expiry, TTL

**Config**:
The inputs a job seeker edits to point Job Scout at their own search: roles, location rules, pay floor, boards, X queries, profile summary, weights, cap and schedule.
_Avoid_: Settings, brief, preferences

### Triage

**Daily ping**:
The set of Telegram messages a scan produces: one header plus one message per lead sent that day. On a day with nothing to send, it is one "no new leads" message with the day's counts.
_Avoid_: Digest, notification, alert

**Daily cap**:
The most leads the daily ping sends, highest fit score first. New leads that miss the cap stay New and compete in later pings until they leave the freshness window. No lead is sent twice.
_Avoid_: Limit, top N

**Lead status**:
Where a lead stands with the job seeker: New, Picked, Applied or Passed. Separately, a lead is **Closed** when its posting disappears from its board; this is recorded quietly and a Closed New lead is no longer sent.
_Avoid_: Stage, column, state

**Pick**:
The job seeker choosing a lead to pursue by tapping Find people. It moves the lead to Picked and returns the apply link, key facts and suggested contacts.
_Avoid_: Select, like, save, interested

**Applied**:
The job seeker has submitted an application for the lead. It can follow New or Picked. Job Scout records it; it never applies.
_Avoid_: Submitted

**Pass**:
The job seeker deciding not to pursue a lead. It moves the lead to Passed and always carries a pass reason.
_Avoid_: Reject, dismiss, skip, archive

**Pass reason**:
One of ten fixed codes explaining a pass, such as `comp_below_range` or `role_family_off`, plus an optional note.
_Avoid_: Feedback, rejection reason
