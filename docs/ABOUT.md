<!-- SPDX-License-Identifier: Apache-2.0 -->
# GitHub repository settings (for the maintainer)

These are the exact strings to paste into the repository's settings. They are kept in the repository so they can be reviewed like any other change. Nothing here is applied automatically.

## About box (Settings, or the gear next to "About")

**Description** (under 350 characters):

```
Research prototype: a memory that sorts itself into groups so a question wakes only a small part of it, with a checkable record on every answer. Explorer of 144 real recorded searches. Apache-2.0.
```

**Website:**

```
https://anshul48.github.io/trace/
```

**Topics** (paste one by one, or with the GitHub CLI: `gh repo edit Anshul48/trace --add-topic ...`):

```
ai-memory, semantic-search, vector-search, retrieval, self-organizing, sparse-activation, provenance, reproducible-research, research-prototype, apache-2-0
```

The checkboxes below the topics: leave "Releases" and "Packages" unticked (there are none); tick "Include in the home page" only if you want the Pages site shown.

## Social preview image

Upload [`docs/img/social-preview.png`](img/social-preview.png) (1280 by 640 pixels) at Settings, General, "Social preview", "Edit", "Upload an image". GitHub does not allow setting it from a file in the repository or from the command line. The source is [`img/social.html`](img/social.html): open it in a browser window sized 1280 by 640 pixels and take a screenshot to regenerate the image.

## GitHub Pages

Settings, Pages, Build and deployment, Source: **GitHub Actions**. The workflow `.github/workflows/pages.yml` publishes the `docs/` folder on every push to `main`.

## Pinned issue and labels (optional)

The issue forms use the labels `bug`, `enhancement` and `claim-check`. Create `claim-check` (suggested colour `#a8283a`) so reports of a wrong number are easy to find.
