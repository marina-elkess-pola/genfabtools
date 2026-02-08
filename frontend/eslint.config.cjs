module.exports = [
  {
    ignores: [
      'backups/**',
      '**/*.backup*.jsx',
      '**/*.user-backup.jsx',
      '_resolve_react.js',
      'build/**',
      'dist/**',
      'static/**',
      'occupancy-calculator/**',
      'public/**',
      'node_modules/**'
    ],
  },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // keep the project's existing preference: allow unused vars with leading uppercase
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }],
    },
  },
];
