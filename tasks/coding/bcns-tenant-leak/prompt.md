A customer just sent us this about the jobs API:

> Hi, I pulled our job export this morning (exportJobs for our account, kestrel-ridge)
> and the file had jobs in it that aren't ours. I recognised a couple of them as another
> company's work orders. Please sort this out; we can't have other clients' data showing
> up in our account.

This repo is the worker behind that API (plain Node, no dependencies; run the tests with
`npm test`). Find the cause and fix it, then add regression tests so it can't come back.
Keep the change focused. Tell me briefly what you found and changed.
