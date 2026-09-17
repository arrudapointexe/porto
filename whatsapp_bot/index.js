const wppconnect = require('@wppconnect-team/wppconnect');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

wppconnect.create({
    session: 'whatsapp_bot',
    puppeteerOptions: {
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    },
    catchQR: (base64Qr, asciiQR) => {
        console.log(asciiQR);
        console.log('Escaneie o QR Code acima com seu WhatsApp!');
    }
}).then((client) => start(client))
  .catch((error) => console.log('❌ Falha ao iniciar WppConnect:', error));

const lastMediaByChat = {};

async function processMedia(client, mediaMsg, chatId, textMsg = null) {
    const replyToMsgId = textMsg ? textMsg.id : mediaMsg.id;
    // Removido o log de "Processando foto" a pedido do usuário
    
    try {
        const messageId = mediaMsg.id || mediaMsg; // Pega o ID com segurança
        const b64 = await client.downloadMedia(messageId);
        if (!b64) {
            await client.reply(chatId, '❌ Não foi possível baixar a imagem da mensagem.', replyToMsgId);
            return;
        }

        // Limpar cabecalho do base64 se existir
        const base64Data = b64.replace(/^data:.*?base64,/, "");

        const mimetype = mediaMsg.mimetype || 'image/jpeg';
        const ext = mimetype.split('/')[1].split(';')[0] || 'jpg';
        const filename = `temp_${Date.now()}.${ext}`;
        const filepath = path.join(__dirname, filename);
        
        fs.writeFileSync(filepath, base64Data, 'base64');
        
        // Chamar Python script
        const pythonPath = 'C:\\bots\\venv\\Scripts\\python.exe';
        const scriptPath = 'C:\\bots\\shopee_at_automator.py';
        
        exec(`"${pythonPath}" "${scriptPath}" "${filepath}"`, async (error, stdout, stderr) => {
            // Excluir a foto
            if (fs.existsSync(filepath)) fs.unlinkSync(filepath);
            
            let output = stdout.trim();
            if (!output && error) {
                output = "❌ Erro ao rodar script: " + error.message;
            } else if (!output) {
                output = "⚠️ Não retornou nenhum resultado. Tente novamente.";
            }
            
            // Responder no wpp
            await client.reply(chatId, output, replyToMsgId);
        });
    } catch (e) {
        console.error("ERRO INTERNO NO PROCESSMEDIA:", e);
        await client.reply(chatId, '❌ Erro interno: ' + e.message, replyToMsgId);
    }
}

function start(client) {
    console.log('✅ Robô do WhatsApp conectado e ouvindo mensagens!');

    client.onAnyMessage(async (msg) => {
        try {
            const chatId = msg.from;
            // No WppConnect, mídias tem base64 no body. Temos que pegar o caption obrigatoriamente.
            const msgText = (msg.type === 'chat') ? (msg.body || '') : (msg.caption || '');
            const temAKeyAt = /teste_at/i.test(msgText); // removido o \b para ser mais flexível
            
            // Log incondicional pra vermos O QUE está chegando, sem floodar com base64
            let snippetBody = (msg.body && msg.body.length > 50) ? "[BASE64_MUITO_GRANDE]" : (msg.body || "");
            console.log(`[LOG DEBUG] type=${msg.type}, isMedia=${msg.isMedia}, caption="${msg.caption}", body="${snippetBody}"`);


            // 1. É uma mensagem de mídia? (No WppConnect, mídias tem type image, video, document, etc)
            if (msg.isMedia || msg.type === 'image' || msg.type === 'video' || msg.type === 'document') {
                lastMediaByChat[chatId] = {
                    msgId: msg.id,
                    msgObj: msg,
                    time: Date.now()
                };
                
                if (temAKeyAt) {
                    await processMedia(client, msg, chatId);
                    delete lastMediaByChat[chatId];
                }
            } 
            // 2. É texto e tem a palavra "teste_at"?
            else if (temAKeyAt) {
                if (msg.quotedMsgId) {
                    const quotedMsg = await client.getMessageById(msg.quotedMsgId);
                    if (quotedMsg && (quotedMsg.isMedia || quotedMsg.type === 'image' || quotedMsg.type === 'video' || quotedMsg.type === 'document')) {
                        await processMedia(client, quotedMsg, chatId, msg);
                        return;
                    }
                }
                
                const lastMedia = lastMediaByChat[chatId];
                if (lastMedia && (Date.now() - lastMedia.time) < 120000) {
                    await processMedia(client, lastMedia.msgObj, chatId, msg);
                    delete lastMediaByChat[chatId];
                }
            }
        } catch (e) {
            console.error('Error handling message', e);
        }
    });
}
