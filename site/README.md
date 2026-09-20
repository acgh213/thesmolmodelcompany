# The Smol Model Company public site

The public research site for [The Smol Model Company of New Haven](https://thesmolmodel.co).
It is an Astro static site with handwritten CSS: no client framework, Tailwind,
or remote analytics.

## Local development

```sh
npm install
npm run dev
```

Build the production bundle with:

```sh
npm run build
```

The output is `dist/`. Review public copy against canonical research documents
before deployment: the site may describe the research program and methods, but
must never invent experiment results, benchmark scores, model identities, or
hardware performance.

## Production deployment

Cloudflare Pages project: `thesmolmodel-co`.

```sh
export CLOUDFLARE_API_TOKEN="…"
export CLOUDFLARE_ACCOUNT_ID="…"
npm run deploy:pages
```

The account token needs only account-level **Cloudflare Pages: Edit** and
zone-level **Zone: Read** plus **DNS: Edit** for `thesmolmodel.co`. Keep it in a
secret manager; never commit it to this repository or put it in `.env` files.

Cloudflare serves the site at:

- `https://thesmolmodel.co`
- `https://www.thesmolmodel.co`
- `https://thesmolmodel-co.pages.dev`
