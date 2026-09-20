# Public site working rules

- This is a static Astro site. Keep it small and understandable: handwritten
  CSS and Astro templates are preferred; do not add React, Tailwind, an SPA
  state layer, analytics, or a CMS without a specific accepted need.
- The visual source of truth is a single coastal-laboratory standard: weathered
  paper, cold instrument green, stamped-rust signal color, monograph typography,
  and physical-document precision.
- Public claims must be grounded in the canonical Forgejo repository. The site
  may state current protocol/design status and link to source documents; it must
  not claim a benchmark result, model capability, hardware fit, or research
  conclusion before the corresponding manifested result is reviewed and public.
- Before a release, run `npm run build`; for repository changes also run the
  root documentation checks from the repository root.
- Deployment credentials stay outside the repository. Cloudflare Pages project
  configuration and the live-domain procedure are documented in `README.md`.
