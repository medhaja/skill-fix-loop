---
name: deploy-preview
description: Build the current web project and deploy it to a Vercel preview URL.
expected_output:
  - "Preview URL:"
---

# Deploy preview

## When to use
Use this when the user asks for a preview link for the current branch of a web project.

## Steps
1. Run `npm ci` to install dependencies.
2. Run `npm run build` and stop if the build fails.
3. Run `vercel build` to produce the prebuilt output.
4. Run `vercel deploy --prebuilt --preview` and capture the URL it prints.
5. Reply with the URL.

## Output
- One line: `Preview URL: <url>`
