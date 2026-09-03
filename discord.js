const { 
    Client, 
    GatewayIntentBits, 
    REST, 
    Routes, 
    SlashCommandBuilder, 
    EmbedBuilder, 
    ActionRowBuilder, 
    ButtonBuilder, 
    ButtonStyle,
    Events
} = require('discord.js');
const express = require('express');
const fs = require('fs');

// Prevent unexpected process crashes
process.on('unhandledRejection', (reason) => console.error('⚠️ [CRASH PREVENTED] Unhandled Rejection:', reason));
process.on('uncaughtException', (err) => console.error('⚠️ [CRASH PREVENTED] Uncaught Exception:', err));

// ==================== CONFIGURATION ====================
const TOKEN = process.env.DISCORD_TOKEN;
const CLIENT_ID = process.env.CLIENT_ID || '1540776513119719591';
const SUPPORTER_ROLE_ID = process.env.SUPPORTER_ROLE_ID;
const SERVER_KEY = process.env.SERVER_KEY || '5839ecdfd43bc7467f77cba4a40ea64c8ee5f986f61cf16a0e024ed2225891a4'; 
const REFRESH_API_URL = 'https://nulls.tools/api/refresh';

// Primary Master Refresh Token
let MASTER_REFRESH_TOKEN = process.env.MASTER_REFRESH_TOKEN || "";

let botSettings = {
    logsChannelId: process.env.LOGS_CHANNEL_ID || "",
    defaultCooldownSeconds: 0 
};

// --- DATABASE TOKEN ROTATION LOADER ---
function getStoredTokens() {
    let tokenList = [];
    
    // Add environment token first if available
    if (MASTER_REFRESH_TOKEN && MASTER_REFRESH_TOKEN.trim().length > 0) {
        tokenList.push(MASTER_REFRESH_TOKEN.trim());
    }

    // Load extra fallback tokens from database.json if available
    if (fs.existsSync('./database.json')) {
        try {
            const dbRaw = fs.readFileSync('./database.json', 'utf8');
            const dbData = JSON.parse(dbRaw);
            if (Array.isArray(dbData.tokens)) {
                dbData.tokens.forEach(item => {
                    try {
                        const parsed = typeof item === 'string' ? JSON.parse(item) : item;
                        if (parsed.refresh_token) {
                            tokenList.push(parsed.refresh_token.trim());
                        }
                    } catch (e) {
                        if (typeof item === 'string' && item.includes('eyJ')) {
                            tokenList.push(item.trim());
                        }
                    }
                });
            }
        } catch (e) {
            console.error('⚠️ Could not parse database.json tokens:', e.message);
        }
    }

    // Remove duplicates
    return [...new Set(tokenList)];
}

// ==================== DISCORD CLIENT SETUP ====================
const client = new Client({ 
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.GuildMembers
    ] 
});

// --- LOGGING HELPER ---
async function sendLog(embed) {
    if (!botSettings.logsChannelId) return;
    try {
        const channel = await client.channels.fetch(botSettings.logsChannelId);
        if (channel && channel.isTextBased()) {
            await channel.send({ embeds: [embed] });
        }
    } catch (e) {
        console.error('❌ Failed to send log:', e.message);
    }
}

// --- LIVE TOKEN GENERATOR ---
async function fetchLiveTokenPair() {
    console.log('⚡ Requesting live token exchange from Nulls API...');
    
    const tokenCandidates = getStoredTokens();
    if (tokenCandidates.length === 0) {
        console.error('❌ No refresh tokens found in environment or database.json.');
        return null;
    }

    // Attempt token exchange across candidates
    for (const activeToken of tokenCandidates) {
        try {
            // Attempt standard field names
            const response = await fetch(REFRESH_API_URL, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'User-Agent': 'SteamVR 1.88.1.3421_a3df6ce5'
                },
                body: JSON.stringify({
                    server_key: SERVER_KEY,
                    refresh_token: activeToken
                })
            });

            if (!response.ok) {
                const errBody = await response.text();
                console.error("❌ Nulls API Status ${response.status} | Details: ${errBody}");
                continue; // Try next candidate
            }

            const data = await response.json();
            const freshBearer = data.token || data.bearer || data.access_token || data.jwt;

            if (freshBearer) {
                return {
                    bearer: freshBearer,
                    refresh_token: data.refresh_token || data.refreshToken || data.refresh || activeToken
                };
            }
        } catch (error) {
            console.error('❌ Network error generating live token:', error.message);
        }
    }

    return null;
}

// --- SLASH COMMANDS REGISTRATION ---
const commands = [
    new SlashCommandBuilder().setName('generator').setDescription('Spawns the live token generator interface.')
].map(c => c.toJSON());

if (TOKEN) {
    const rest = new REST({ version: '10' }).setToken(TOKEN);
    rest.put(Routes.applicationCommands(CLIENT_ID), { body: commands })
        .then(() => console.log('✅ Slash commands registered successfully.'))
        .catch(console.error);
}

// --- BOT EVENTS ---
client.once(Events.ClientReady, (readyClient) => {
    console.log("🚀 ONLINE: Logged in as ${readyClient.user.tag}");
});

client.on(Events.InteractionCreate, async interaction => {
    // Command handler: /generator
    if (interaction.isChatInputCommand() && interaction.commandName === 'generator') {

    if (!interaction.member.roles.cache.has(SUPPORTER_ROLE_ID)) {
        return interaction.reply({
            content: '❌ You need the Supporter role to use this command.',
            ephemeral: true
        });
    }


        const embed = new EmbedBuilder()
            .setTitle('⚙️ 4's Token Generator')
            .setDescription('Click the button below to generate a token!')
            .setColor('#5865F2');

        const row = new ActionRowBuilder().addComponents(
            new ButtonBuilder()
                .setCustomId('claim_token')
                .setLabel('Generate Live Token')
                .setStyle(ButtonStyle.Success)
        );

        await interaction.reply({ embeds: [embed], components: [row] });
        return;
    }

    // Button handler: claim_token
    if (interaction.isButton() && interaction.customId === 'claim_token') {
        await interaction.deferReply({ flags: 64 });

        const tokenPair = await fetchLiveTokenPair();

        if (!tokenPair) {
            return interaction.editReply({ 
                content: '❌ Generation failed. Check server logs for API error details.' 
            });
        }

        const dmPayload = JSON.stringify({
            _note: "Fresh live token pair generated successfully",
            bearer: tokenPair.bearer,
            refresh_token: tokenPair.refresh_token
        }, null, 2);

        try {
            await interaction.user.send(` **Your Live Tokens:**\n\`\`\`json\n${dmPayload}\n\`\`\``);
            await interaction.editReply({ content: '📦 Check your Direct Messages for your fresh token!' });

            const logEmbed = new EmbedBuilder()
                .setTitle('📜 Token Generated')
                .addFields(
                    { name: 'User', value: `${interaction.user.tag} (\`${interaction.user.id}\`)`, inline: true }
                )
                .setTimestamp()
                .setColor('#57F287');
            await sendLog(logEmbed);

        } catch (e) {
            await interaction.editReply({ content: '❌ Direct Messages are closed. Please open your DMs and try again.' });
        }
    }
});

// ==================== WEB SERVER FOR RAILWAY ====================
const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.get('/', (req, res) => {
    res.send(`<h2>⚙️ Private Token Bot Online</h2>`);
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`🌐 Web server active on port ${PORT}`);
});

if (TOKEN) {
    client.login(TOKEN);
} else {
    console.error('❌ DISCORD_TOKEN is missing from environment variables!');
}
