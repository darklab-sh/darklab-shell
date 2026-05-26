export default {
  rules: {
    'block-no-empty': true,
    'color-no-invalid-hex': true,
    'declaration-block-no-duplicate-custom-properties': true,
    'declaration-block-no-duplicate-properties': [
      true,
      {
        ignore: ['consecutive-duplicates-with-different-values'],
      },
    ],
    'font-family-no-duplicate-names': true,
    'function-no-unknown': [
      true,
      {
        ignoreFunctions: ['color-mix'],
      },
    ],
    'keyframe-block-no-duplicate-selectors': true,
    'media-feature-name-no-unknown': true,
    'no-descending-specificity': null,
    'no-duplicate-at-import-rules': true,
    'no-duplicate-selectors': null,
    'no-invalid-position-at-import-rule': true,
    'property-no-unknown': [
      true,
      {
        ignoreProperties: ['line-clamp'],
      },
    ],
    'selector-pseudo-class-no-unknown': true,
    'selector-pseudo-element-no-unknown': true,
    'unit-no-unknown': true,
  },
};
