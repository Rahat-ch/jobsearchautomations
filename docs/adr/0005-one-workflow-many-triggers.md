# One workflow with several triggers

An n8n template-gallery submission is a single workflow JSON, and importing a template creates exactly one workflow (n8n 2.41.3, `createWorkflowFromTemplate`). So Job Scout lives in one workflow with several triggers instead of a main workflow plus sub-workflows:
- the daily scan schedule
- webhooks for Find people, Applied and Referral
- the Pass form
- the "set lead status" trigger that agents reach over MCP (instance-level MCP can target a trigger by name)

Each execution runs only one trigger. Importing a template drops workflow settings, so anything that lives in settings must be set up by hand after import and documented in a sticky note.

The crash alert turned out not to need a setting (issue #10, n8n 2.41.3): when a workflow has an Error Trigger and no error workflow set, n8n runs that workflow's own Error Trigger when a published run fails. So the alert lives in this same workflow and survives import.
