# Satyrn Dataset Viewer — frontend

TypeScript + React single-page app that renders a generated JSONL dataset. It is built by
Vite into `../src/satyrn/dataset/viewer/static/` and served by the Flask backend.

## Development

Start the backend against a dataset:

```bash
cd ..
satyrn-dataset viewer ../datasets/test/RL-test-3.14-code_demo-rote.jsonl --port 5000
```

Then run the Vite dev server (it proxies `/api` to Flask):

```bash
npm install
npm run dev
```

## Production build

```bash
npm install
npm run build
```

The backend will then serve the app at `http://127.0.0.1:5000/`.

## Tests

```bash
npm test
```

This verifies that prompts and conversation messages are rendered as markdown,
that prompts/completions are combined into user/assistant turns, and that fenced
(labelled or unlabelled) code blocks receive Python syntax highlighting.
