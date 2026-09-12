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
const path = require('path');

const BASE_DIR = __dirname;

// Prevent unexpected process crashes
process.on('unhandledRejection', (reason) =>
    console.error('⚠️ [CRASH PREVENTED] Unhandled Rejection:', reason)
);

process.on('uncaughtException', (err) =>
    console.error('⚠️ [CRASH PREVENTED] Uncaught Exception:', err)
);


// ==================== CONFIGURATION ====================

const TOKEN = process.env.DISCORD_TOKEN;
const CLIENT_ID = process.env.CLIENT_ID;

const SERVER_IDS = [
    '1540776513119719591'
];

const SUPPORTER_ROLE_IDS = [
    '1539068588210651156',
    '1544791353366679682',
    '1545535562763468990'
];

// Railway variable first.
// If Railway somehow fails to provide it, the hard-coded fallback is used.
const SERVER_KEY =
    process.env.SERVER_KEY || '6URuTSlDKKfYbuDW';



// Initial/bootstrap refresh token.
// The current rotated token will be stored in database.json.
let MASTER_REFRESH_TOKEN =
    process.env.MASTER_REFRESH_TOKEN || '';


// ==================== REFRESH TOKEN STORAGE ====================

function saveRefreshToken(newRefreshToken) {
    if (!newRefreshToken || !newRefreshToken.trim()) {
        return;
    }

    MASTER_REFRESH_TOKEN = newRefreshToken.trim();

    try {
        const dbPath = path.join(BASE_DIR, 'database.json');

        let dbData = {};

        if (fs.existsSync(dbPath)) {
            dbData = JSON.parse(
                fs.readFileSync(dbPath, 'utf8')
            );
        }

        if (!Array.isArray(dbData.tokens)) {
            dbData.tokens = [];
        }

        dbData.tokens[0] = {
            refresh_token: MASTER_REFRESH_TOKEN
        };

        fs.writeFileSync(
            dbPath,
            JSON.stringify(dbData, null, 2)
        );

        console.log('✅ Saved newest refresh token.');
    } catch (error) {
        console.error(
            '❌ Failed to save refresh token:',
            error.message
        );
    }
}


// ==================== COOLDOWNS ====================

const userCooldowns = new Map();

let botSettings = {
    logsChannelId: process.env.LOGS_CHANNEL_ID || '',
    defaultCooldownSeconds: 600
};


// Cooldowns are in seconds

const roleCooldowns = {
    '1544790700690767902': 3,
    '1544791353366679682': 210,
    '1544791985204756511': 30
};


// ==================== TOKEN DATABASE ====================

// --- DATABASE TOKEN ROTATION LOADER ---
function getStoredTokens() {
    const tokenList = [];

    // Prefer the newest token saved by the Nakama refresher.
    if (fs.existsSync('./database.json')) {
        try {
            const dbRaw = fs.readFileSync('./database.json', 'utf8');
            const dbData = JSON.parse(dbRaw);

            if (Array.isArray(dbData.tokens)) {
                for (const item of dbData.tokens) {
                    try {
                        const parsed =
                            typeof item === 'string'
                                ? JSON.parse(item)
                                : item;

                        if (
                            parsed &&
                            typeof parsed.refresh_token === 'string' &&
                            parsed.refresh_token.trim().length > 0
                        ) {
                            tokenList.push(parsed.refresh_token.trim());
                        }
                    } catch {
                        // Ignore malformed database entries
                    }
                }
            }
        } catch (error) {
            console.error(
                '⚠️ Could not parse database.json tokens:',
                error.message
            );
        }
    }

    // Railway MASTER_REFRESH_TOKEN is only a fallback.
    if (
        MASTER_REFRESH_TOKEN &&
        MASTER_REFRESH_TOKEN.trim().length > 0
    ) {
        tokenList.push(MASTER_REFRESH_TOKEN.trim());
    }

    // Remove duplicates while preserving order.
    return [...new Set(tokenList)];
}

// ==================== DISCORD CLIENT ====================

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.GuildMembers
    ]
});


// ==================== LOGGING ====================

async function sendLog(embed) {
    if (!botSettings.logsChannelId) {
        return;
    }

    try {
        const channel =
            await client.channels.fetch(
                botSettings.logsChannelId
            );

        if (
            channel &&
            channel.isTextBased()
        ) {
            await channel.send({
                embeds: [embed]
            });
        }
    } catch (e) {
        console.error(
            '❌ Failed to send log:',
            e.message
        );
    }
}


// --- NAKAMA TOKEN REFRESH ---
async function fetchLiveTokenPair() {
    console.log('⚡ Requesting fresh token directly from Nakama...');

    const tokenCandidates = getStoredTokens();

    if (tokenCandidates.length === 0) {
        console.error('❌ No refresh tokens found in environment or database.json.');
        return null;
    }

    if (!SERVER_KEY) {
        console.error('❌ Nakama SERVER_KEY is missing.');
        return null;
    }

    const refreshUrl = `${NAKAMA_HOST}/v2/account/session/refresh`;

    // Nakama uses HTTP Basic authentication:
    // username = server key
    // password = empty
    const basicAuth = Buffer
        .from(`${SERVER_KEY}:`)
        .toString('base64');

    for (const refreshToken of tokenCandidates) {
        try {
            const response = await fetch(refreshUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Basic ${basicAuth}`
                },
                body: JSON.stringify({
                    token: refreshToken
                })
            });

            const responseText = await response.text();

            if (!response.ok) {
                console.error(
                    `❌ Nakama refresh failed: ${response.status} | ${responseText}`
                );
                continue;
            }

            let data;

            try {
                data = JSON.parse(responseText);
            } catch {
                console.error('❌ Nakama returned invalid JSON.');
                continue;
            }

            const freshBearer =
                data.token ||
                data.access_token;

            const freshRefreshToken =
                data.refresh_token ||
                data.refreshToken ||
                refreshToken;

            if (!freshBearer) {
                console.error('❌ Nakama response did not contain a new access token.');
                continue;
            }

            console.log('✅ Nakama token refresh successful.');

            // Update the in-memory master refresh token
            MASTER_REFRESH_TOKEN = freshRefreshToken;

            // Save the rotated refresh token to database.json
            try {
                let dbData = {};

                if (fs.existsSync('./database.json')) {
                    try {
                        dbData = JSON.parse(
                            fs.readFileSync('./database.json', 'utf8')
                        );
                    } catch {
                        dbData = {};
                    }
                }

                if (!Array.isArray(dbData.tokens)) {
                    dbData.tokens = [];
                }

                dbData.tokens[0] = {
                    refresh_token: freshRefreshToken
                };

                fs.writeFileSync(
                    './database.json',
                    JSON.stringify(dbData, null, 2)
                );

                console.log('💾 Saved newest Nakama refresh token.');
            } catch (saveError) {
                console.error(
                    '⚠️ Could not save refreshed token:',
                    saveError.message
                );
            }

            return {
                bearer: freshBearer,
                refresh_token: freshRefreshToken
            };

        } catch (error) {
            console.error(
                '❌ Network error refreshing Nakama token:',
                error.message
            );
        }
    }

    console.error('❌ All Nakama refresh attempts failed.');
    return null;
}


// ==================== SLASH COMMAND ====================

const commands = [
    new SlashCommandBuilder()
        .setName('generator')
        .setDescription(
            'Spawns the live token generator interface.'
        )
].map(c => c.toJSON());


if (TOKEN) {

    const rest =
        new REST({
            version: '10'
        }).setToken(TOKEN);


    for (const serverId of SERVER_IDS) {

        rest.put(
            Routes.applicationGuildCommands(
                CLIENT_ID,
                serverId
            ),
            {
                body: commands
            }
        )
        .then(() =>
            console.log(
                `✅ Slash commands registered in ${serverId}`
            )
        )
        .catch(console.error);
    }
}


// ==================== BOT EVENTS ====================

client.on(
    Events.InteractionCreate,
    async interaction => {

        // ==================== /generator ====================

        if (
            interaction.isChatInputCommand() &&
            interaction.commandName === 'generator'
        ) {

            if (
                !interaction.member.roles.cache.some(
                    role =>
                        SUPPORTER_ROLE_IDS.includes(
                            role.id
                        )
                )
            ) {

                return interaction.reply({
                    content:
                        '❌ You need the Supporter role to use this command.',

                    ephemeral: true
                });
            }


            const embed =
                new EmbedBuilder()
                    .setTitle(
                        "⚙️ 4's Token Generator"
                    )
                    .setDescription(
                        'Click the button below to generate a token!'
                    )
                    .setColor('#5865F2');


            const row =
                new ActionRowBuilder()
                    .addComponents(

                        new ButtonBuilder()
                            .setCustomId(
                                'claim_token'
                            )
                            .setLabel(
                                'Generate Live Token'
                            )
                            .setStyle(
                                ButtonStyle.Success
                            )

                    );


            await interaction.reply({
                embeds: [embed],
                components: [row]
            });

            return;
        }


        // ==================== BUTTON ====================

        if (
            interaction.isButton() &&
            interaction.customId === 'claim_token'
        ) {

            const userId =
                interaction.user.id;

            const now =
                Date.now();


            let cooldownSeconds =
                botSettings.defaultCooldownSeconds;


            if (
                interaction.member &&
                interaction.member.roles
            ) {

                for (
                    const [
                        roleId,
                        roleCooldown
                    ]
                    of Object.entries(
                        roleCooldowns
                    )
                ) {

                    if (
                        interaction.member.roles.cache.has(
                            roleId
                        )
                    ) {

                        cooldownSeconds =
                            Math.min(
                                cooldownSeconds,
                                roleCooldown
                            );
                    }
                }
            }


            const lastUsed =
                userCooldowns.get(
                    userId
                );


            if (lastUsed) {

                const elapsed =
                    (now - lastUsed) /
                    1000;

                const remaining =
                    cooldownSeconds -
                    elapsed;


                if (remaining > 0) {

                    const minutes =
                        Math.floor(
                            remaining / 60
                        );

                    const seconds =
                        Math.ceil(
                            remaining % 60
                        );


                    return interaction.reply({
                        content:
                            `⏳ You are on cooldown. Please wait **${minutes}m ${seconds}s** before generating another token.`,

                        ephemeral: true
                    });
                }
            }


            await interaction.deferReply({
                flags: 64
            });


            const tokenPair =
                await fetchLiveTokenPair();


            if (!tokenPair) {

                return interaction.editReply({
                    content:
                        '❌ Generation failed. Current tokens have expired and will be restocked soon.'
                });
            }


            const dmPayload =
                JSON.stringify(
                    {
                        _note:
                            "thanks for using 4's token gen",

                        bearer:
                            tokenPair.bearer,

                        refresh_token:
                            tokenPair.refresh_token
                    },
                    null,
                    2
                );


            try {

                await interaction.user.send(
                    `**Your Token :**\n\`\`\`json\n${dmPayload}\n\`\`\``
                );


                userCooldowns.set(
                    userId,
                    Date.now()
                );


                const cooldownMinutes =
                    Math.ceil(
                        cooldownSeconds / 60
                    );


                await interaction.editReply({
                    content:
                        `📦 Check your Direct Messages for your token!\n⏳ Your next token will be available in **${cooldownMinutes} minute${cooldownMinutes === 1 ? '' : 's'}**.`
                });


                const logEmbed =
                    new EmbedBuilder()
                        .setTitle(
                            '📜 Token Generated'
                        )
                        .addFields({
                            name: 'User',

                            value:
                                `${interaction.user.tag} (\`${interaction.user.id}\`)`,

                            inline: true
                        })
                        .setTimestamp()
                        .setColor('#57F287');


                await sendLog(
                    logEmbed
                );


            } catch (e) {

                await interaction.editReply({
                    content:
                        '❌ Direct Messages are closed. Please open your DMs and try again.'
                });
            }
        }
    }
);


// ==================== RAILWAY WEB SERVER ====================

const app = express();

app.use(
    express.json()
);

app.use(
    express.urlencoded({
        extended: true
    })
);


app.get(
    '/',
    (req, res) => {

        res.send(
            `<h2>⚙️ Private Token Bot Online</h2>`
        );
    }
);


const PORT =
    process.env.PORT || 3000;


app.listen(
    PORT,
    () => {

        console.log(
            `🌐 Web server active on port ${PORT}`
        );
    }
);


// ==================== LOGIN ====================

if (TOKEN) {

    client.login(TOKEN);

} else {

    console.error(
        '❌ DISCORD_TOKEN is missing from environment variables!'
    );
}