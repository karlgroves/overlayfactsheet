# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the Overlay Fact Sheet (https://overlayfactsheet.com/), a static multilingual Hugo site that provides factual information about web accessibility overlays. The site is a community-driven, non-biased educational resource signed by accessibility professionals.

## Architecture

### Hugo Static Site Generator
- Uses Hugo v0.93.3 (specified in netlify.toml)
- Single-page application with all content on the homepage
- No Hugo installation required locally (builds via Netlify)

### Multilingual Structure
The site supports multiple languages (English, French, Portuguese Brazilian, Japanese, Indonesian, German, Dutch) using Hugo's i18n system:

- **Translation files**: `i18n/{language-code}.yml` - Each file contains key-value pairs for all translatable content
- **Language configuration**: `config.toml` - Defines all available languages with their weights, names, and content directories
- **Template**: `layouts/index.html` - Single template that uses `{{ T "key" }}` to pull translated strings
- **Fallback**: Missing translation keys automatically fall back to English

### Content Model
Unlike typical Hugo sites, this project has no markdown content files. All text content lives in the `i18n/*.yml` files as translation strings. The `layouts/index.html` template structures the page and pulls in translated content via Hugo's `T` function.

### File Structure
- `config.toml` - Hugo configuration and language definitions
- `i18n/` - Translation files (one per language)
- `layouts/index.html` - Main HTML template
- `static/` - CSS, images, favicon
- `netlify.toml` - Deployment configuration

## Common Commands

### Build
```bash
hugo --gc --minify
```

### Local Development
```bash
hugo server
```
This starts a development server with live reload. The site will be available at http://localhost:1313/

### Preview with Future Content
```bash
hugo server --buildFuture
```

## Development Workflow

### Branch Strategy
- `main` - Production branch (auto-deploys to overlayfactsheet.com)
- `develop` - Staging branch (deploys to preview URL)
- Feature branches - Created from `develop`, PRs target `develop`

The workflow is: feature branch → `develop` → verify on preview → PR to `main` → production deploy

### Adding or Editing Content

#### To modify existing translations:
1. Edit the appropriate `i18n/{language-code}.yml` file
2. Find the translation key (e.g., `topic01p01`)
3. Update the `translation:` value

#### To add a new language:
1. Add language configuration to `config.toml` under `[languages]`:
   ```toml
   [languages.{code}]
     contentDir = 'i18n/{code}'
     weight = {number}
     [languages.{code}.params]
       languageName = '{full name}'
       languageNameShort = '{code}'
       languageCode = '{code}'
   ```
2. Create `i18n/{code}.yml` with all translation keys from `i18n/en.yml`
3. Translate each value

### Adding Endorsements
Endorsements are in `layouts/index.html` as an ordered list (`<ol>`) after the "Signed by" heading. Add new `<li>` entries in the format: `Name, Title, Organization` or `Name, self`. Do not add links.

## Deployment

- Hosted on Netlify
- Production: `main` branch → https://overlayfactsheet.com/
- Preview: `develop` branch and PRs get unique preview URLs
- Build command: `hugo --gc --minify`
- Publish directory: `public`

## Important Constraints

- **No package.json**: This is a pure Hugo site with no Node.js dependencies
- **Content is fact-based**: Avoid hyperbole, exaggeration, and logical fallacies
- **No SEO links**: Endorsements must not include links
- **HTML in translations**: Translation strings can contain HTML (rendered with `| safeHTML` in templates)
- **No subdirectories**: All content is on a single page, no blog posts or separate pages


## Git Flow Branching Strategy

**MANDATORY**: This project uses Git Flow branching strategy. All development must follow these rules:

### Branch Structure
- **main** - Production-ready code only. Protected branch.
- **develop** - Integration branch for features. All feature branches merge here first.
- **feature/** - New features (branch from develop, merge to develop)
- **release/** - Release preparation (branch from develop, merge to main and develop)
- **hotfix/** - Emergency production fixes (branch from main, merge to main and develop)

### Workflow Rules
1. Never commit directly to main or develop
2. All work starts from develop branch
3. Create feature branches for new work: `git checkout -b feature/description`
4. Create PRs to merge features into develop
5. Release branches prepare code for production
6. Hotfixes are the only branches created from main
7. Always delete feature branches after merging

## Reviewing PRs

Whenever I ask to review a PR (pull request), use the `pr-review` skill.
