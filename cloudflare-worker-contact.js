/**
 * SITRA / NIRIKX - Relais securise pour le formulaire de contact
 *
 * Ce petit programme tourne sur Cloudflare Workers (pas dans le
 * navigateur du visiteur) : c'est lui qui detient la cle Resend en
 * secret et envoie l'email. Le site public (index.html) ne connait
 * jamais la cle, il appelle juste l'adresse de ce Worker.
 *
 * Mise en place :
 * 1. Cloudflare Dashboard -> Workers & Pages -> Create -> Create Worker
 * 2. Coller ce code dans l'editeur, puis "Deploy"
 * 3. Settings -> Variables and Secrets -> Add -> nom "RESEND_API_KEY",
 *    valeur = la cle Resend (type "Secret", pas "Text")
 * 4. Recuperer l'adresse du Worker (ex: nirikx-contact.xxx.workers.dev)
 */

const DEST_EMAIL = "yanisaidoune1@gmail.com"; // adresse qui recoit les messages

export default {
  async fetch(request, env) {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405, headers: corsHeaders });
    }

    try {
      const { nom, email, msg } = await request.json();

      if (!nom || !email || !msg) {
        return new Response(JSON.stringify({ error: "Champs manquants" }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      const resendResponse = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${env.RESEND_API_KEY}`,
        },
        body: JSON.stringify({
          from: "NIRIKX Contact <onboarding@resend.dev>",
          to: [DEST_EMAIL],
          subject: `[NIRIKX Contact] ${nom} - ${email}`,
          html: `<h2>Nouveau message NIRIKX</h2><p><b>Nom :</b> ${nom}</p><p><b>Email :</b> ${email}</p><p><b>Message :</b><br>${msg.replace(/\n/g, "<br>")}</p>`,
        }),
      });

      if (!resendResponse.ok) {
        const detail = await resendResponse.text();
        return new Response(JSON.stringify({ error: "Echec envoi email", detail }), {
          status: 502,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      return new Response(JSON.stringify({ success: true }), {
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: "Erreur serveur" }), {
        status: 500,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }
  },
};
