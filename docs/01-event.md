# Event, deadlines and accounts

## Deadlines

The Agentic AI Hack Zürich is organized by Tech Europe with Google DeepMind on 10 October 2026. Its public page lists **19:00 competition opt-in**, **20:00 demos**, and **20:45 awards**. The latest user target is **ready by 17:00**, replacing the earlier 19:30 technical deadline and leaving time before the event activities. Competition registration remains separate. Source: [Luma event page](https://luma.com/zrh-hack), consulted on 10 October.

The page names Google DeepMind and J floor as co-hosts, and Gradium and Entire as technology partners, with credits announced. The consulted public text does not state a two-partner requirement: that minimum is an explicit user requirement. The user's preferred combination is **Gradium + Google DeepMind**. Numeric judging weights, pitch duration and submission instructions still need confirmation from the organizers.

## Criteria in the supplied brief

Local primary source: `[External] Google DeepMind x {Tech_ Europe}_ Agentic AI Hack Zürich brief.pdf`, pages 1–5. The brief calls for an agent that helps real people, plans, uses tools, finishes work and can be demonstrated live. People must remain in control of irreversible actions.

The brief and Builder Guide email emphasize Gemini, the Interactions API and managed agents. Our project should demonstrate a concrete transition from a request to a verified artifact, including observable tool execution and results.

The brief names `gemini-3.8-flash` for reasoning and generation and `antigravity-preview-09-2026` for sandbox work. Official documentation confirms these IDs. Minimal model access, managed execution/artifact retrieval and two actual generated AppSpecs have passed; see [managed generation evidence](research/managed-probe.md). Real Gradium speech and generated-app installation remain unverified. The implementation uses REST; [Gemini research](research/gemini.md) also records SDK requirements for future alternatives.

## Temporary account

Source: `How to use a temporary account for a hackthon_ [Shared externally].pdf`, particularly pages 1–5 and 13–14.

- Use the supplied temporary project in AI Studio; import it on the API keys page if it does not appear.
- A separate browser profile prevents confusion with personal accounts.
- Check actual quotas in the account. Guide screenshots do not establish present capacity or availability.
- The account and associated services may be deleted shortly after the event, including the following day. Temporary Cloud Run access is not permanent hosting.
- Save source code, artifacts and demo materials locally before the event ends.
- The guide prohibits quota abuse and publishing API keys. Keep retries bounded and secrets out of logs.

`Gmail - Agentic AI Hack Account Information.pdf` contains access details. Keep that file private and excluded from commits. Public context records only its existence. Minimal provider authentication is now confirmed; see [probe evidence](research/provider-probe.md).

## Mapping the project to the criteria

| Brief criterion | Evidence to demonstrate |
| --- | --- |
| Acts and finishes work | Builds AppSpec, executes checks, repairs an error when needed and produces a package |
| Helps a real person | A non-programmer turns a spoken sketch into a dedicated interactive device app |
| Human control | The user chooses a paired device and presses Generate and install; package activation is reversible and the prior app remains recoverable |
| Works live | One new input, two real providers, acknowledged installation and visible interaction on the device |

This is our project strategy, not an official scoring rubric. A separate preview approval is not required for the main demo: the explicit generation action authorizes the bounded, reversible app deployment. Operations outside that scope, such as erasing user data or changing firmware, are not authorized by that button.

The demo, product interface and all project artifacts are in English, as confirmed by the user.
