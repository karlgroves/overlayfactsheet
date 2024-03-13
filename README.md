# overlay factsheet 

[![Netlify Status](https://api.netlify.com/api/v1/badges/38981166-3465-41df-8561-55859185211c/deploy-status)](https://app.netlify.com/sites/overlayfactsheet/deploys)

A non-biased, community-driven, fact-based information sheet aimed at educating customers on web-accessibility overlays. This repo powers the site at https://overlayfactsheet.com/

## Contributing

### Endorse this statement

Please note: The content of the Overlay Factsheet may change over time. Specifically, content may be added, edited, or removed to provide additional clarity, additional evidence, or other changes in keeping with the goal of sharing facts on overlays. Please understand this before requesting your signature be added. These changes are and will be made in a good faith effort to continue to raise awareness of overlays, their traits, strengths, and weaknesses.  Please be sure to "Watch" this repo to review if any of the changes are consequential enough to change your endorsement.


#### EASY:  If the whole PR thing is something you're not comfortable with you can do one of three things:

 * Log an Issue in this repo: Click "Issues" and follow the process of adding an issue that indicates that you want to sign
 * Send an email to karlgroves@gmail.com to indicate that you want to sign
 * Send a Twitter DM to @karlgroves to indicate that you want to sign

#### Harder, but more efficient

Toward the bottom of the page in the `/src/index.html` file is a heading that says "Signed by".

Below that is an ordered list (`<ol>`);

Add your name as a `<li>` in that list, in the following format:  Name, Title, Organization. For example: `Joe Schmoe, CEO, Acme Corp.`  If you'd rather not put your title and organization down, that's fine.  Feel free to do something like `Joe Schmoe, self`

Please do not add links in the endorsement section. This isn't an exercise in SEO for anyone, it is a statement of unity.

Please use the PR process described below, issuing your PR against the `develop` branch.

### Edit content in an existing language or add a new language

If you want to modify an existing language, simply go to the corresponding file in the `i18n/` folder, e.g. `i18n/en.yml` (for english) and modify the contents. If a translation key doesn't exist, it automatically switches to english content.

If you want to add a new language, it's only a 2-step process:
1. In the `hugo.toml` file, add the new language, e.g. spanish in third position
```
[languages]
  [languages.en]
    contentDir = 'i18n/en'
    weight = 1
    [languages.en.params]
      languageName = 'english'
      languageNameShort = 'en'
      languageCode = 'en'
  [languages.fr]
    contentDir = 'i18n/fr'
    weight = 2
    [languages.fr.params]
      languageName = 'français'
      languageNameShort = 'fr'
      languageCode 'fr'
  [languages.es]
    contentDir = 'i18n/es'
    weight = 3
    [languages.fr.params]
      languageName = 'español'
      languageNameShort = 'es'
      languageCode = 'es'
```
2. In the `i18n/` folder, add a yml file with the language shortname, e.g. `i18n/es.yml` (if spanish), and translate each key in this file.

### Design and/or Code

Contributions to the design and/ or code are encouraged!

We follow a modified "git flow" type of workflow:

1. Create an issue that describes the change you want to make (or pick one from the list of desired changes)
2. Create a branch for that issue
3. Issue a pull request against the `develop` branch that is *solely focused* on the issue you're working against.
4. Once a repo admin approves the PR, it will be merged into `develop`
5. From there, it'll be verified on the preview version of the site and, if acceptable, a PR will be made to go from `develop` to `main`.
6. When the PR to `main` has passed, it will automatically deploy.

### Content

Contributions of content will follow the exact same workflow as above.

Please note the following general content guidance:

1. This project is aimed at conveying facts. Content should strive to avoid hyperbole, exaggeration, and logical fallacy.
2. Opinions should be avoided unless they are opinions of end users describing their experiences with overlays.
3. Advertisements for any product, service, or company is prohibited.
4. You should use [Wikipedia's Content Standards](https://en.wikipedia.org/wiki/Wikipedia:Understanding_Wikipedia%27s_content_standards) and [Principles](https://en.wikipedia.org/wiki/Wikipedia:Principles) as guides for what we're trying to accomplish here.


