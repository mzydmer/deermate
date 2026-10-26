# Frontend sources and motion provenance

DeerMate-owned UI, the original deer mark and `motion/generate.py` / generated scene are covered by the repository MIT license. The frontend is an overlay on DeerFlow commit `a1b89d0432de4e45adc59f512cb25bb386ea1e51`, retaining its license and authentication/API implementation.

The sliding-tab CSS in `overlay/src/styles/deermate.css` is used inside this product from Jakub Antalik's transitions.dev skill at `6a7d68260d624eb66661cc3af17e0989476f48ae`. Its license permits copying/modifying transitions in products and websites, and prohibits publishing a competing transitions collection. DeerMate does not redistribute that collection or the installed skills. See [the author's license](https://github.com/Jakubantalik/transitions.dev/blob/6a7d68260d624eb66661cc3af17e0989476f48ae/skills/transitions-dev/LICENSE.txt). Motion timings are tuned using transitions-polish's usage-based scale, with keyboard/reduced-motion guards.

`overlay/public/deermate/vendor/lottie-light-5.13.0.min.js` is lottie-web 5.13.0, MIT, copyright Airbnb, Inc.; its complete license is adjacent. The pinned npm archive's SHA512 integrity was verified before extracting the player, without running package scripts. The runtime is self-hosted and loads only the bundled original animation.

The text-to-lottie skill comes from Diffusion Studio `diffusionstudio/lottie` at `3c72912fad543897f90045ed4d355813837927fc`. Its official Skia Skottie player is used in the ignored local verification workspace; its project/skill is not bundled into the application. Canonical scene path: `motion/public/projects/deermate/scene-1/lottie.json`; the build copies it to `/deermate/secretary.json`.
