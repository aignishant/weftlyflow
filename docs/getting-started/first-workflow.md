# Your first workflow

*Drafted for Phase 1. Will be rewritten once the first nodes ship.*

The goal will be:

1. Open http://localhost:5173 in a browser.
2. Sign up (first user becomes the instance owner).
3. Click **New workflow**.
4. Drag a **Manual Trigger** onto the canvas.
5. Drag an **HTTP Request** node; connect it to the trigger.
6. Set the URL to `https://api.github.com/repos/python/cpython`.
7. Click **Execute workflow**.
8. Inspect the output in the bottom panel — you should see the repo metadata.

Next up: add a **Set** node to extract `{{ $json.stargazers_count }}`, then an **If** node that branches when the count exceeds 50,000.
