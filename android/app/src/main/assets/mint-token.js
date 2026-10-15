// Public-session WebPoClient integration. No account cookies are imported.
// Protocol reference: yt-dlp-getpot-wpc, maintained by coletdjnz.
async function sonkipMint(binding) {
    for (let attempt = 0; attempt < 20; attempt++) {
        const factory = window.top['havuokmhhs-0']?.bevasrs?.wpc;
        if (factory) {
            try {
                const client = await factory();
                const token = await client.mws({c: binding, mc: false, me: false});
                if (typeof token !== 'string' || !token) throw new Error('YouTube returned an empty token');
                return token;
            } catch (error) {
                if (!String(error).includes('SDF:notready')) throw error;
            }
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
    }
    throw new Error('YouTube public token provider is unavailable. Please try again later.');
}
