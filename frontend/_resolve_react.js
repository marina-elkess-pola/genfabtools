console.log('cwd', process.cwd());
try {
    console.log('react ->', require.resolve('react'));
} catch (e) { console.log('react resolve error', e.message); }
try {
    console.log('react-dom ->', require.resolve('react-dom'));
} catch (e) { console.log('react-dom resolve error', e.message); }
