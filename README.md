# overlay factsheet 

[![Netlify Status](https://api.netlify.com/api/v1/badges/38981166-3465-41df-8561-55859185211c/deploy-status)](https://app.netlify.com/sites/overlayfactsheet/deploys)

A non-biased, community-driven, fact-based information sheet aimed at educating customers on web-accessibility overlays. This repo powers the site at https://overlayfactsheet.com/

## Contributing

### Endorse this statement

#### EASY:  If the whole PR thing is something you're not comfortable with you can do one of three things:

 * Log an Issue in this repo: Click "Issues" and follow the process of adding an issue that indicates that you want to sign
 * Send an email to karl@tenon.io to indicate that you want to sign
 * Send a Twitter DM to @karlgroves to indicate that you want to sign

#### Harder, but more efficient

Toward the bottom of the page in the `/src/index.html` file is a heading that says "Signed by".

Below that is an ordered list (`<ol>`);

Add your name as a `<li>` in that list, in the following format:  Name, Title, Organization. For example: `Joe Schmoe, CEO, Acme Corp.`  If you'd rather not put your title and organization down, that's fine.  Feel free to do something like `Joe Schmoe, self`

Please do not add links in the endorsement section. This isn't an exercise in SEO for anyone, it is a statement of unity.

Please use the PR process described below, issuing your PR against the `develop` branch.

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


