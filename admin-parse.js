/* ===================== LECTEUR DE COLLAGE — DÉCISIONS ADMINISTRATIVES =====================
   Fonction pure (aucun accès au DOM ni au réseau, testable sous Node) qui lit ce que la
   rédaction colle dans « Publications récentes → Ajouter des décisions administratives » :

   - le texte copié de la liste de résultats de justice.public.lu (juridictions
     administratives) : numéro de fichier + date, TYPE DE CONTENTIEUX, INSTANCE, CHAMBRE,
     N° … du rôle, ECLI, « Audience publique du … », résumé du recours ;
   - et/ou des adresses de PDF de ja.public.lu (…/45001-50000/49856.pdf).

   Aucune adresse n'est jamais interrogée par le module : ja.public.lu interdit les robots
   (robots.txt). Les liens sont seulement mémorisés, ou reconstruits pour être ouverts par un
   clic de l'utilisateur.

   Chaque champ est validé avec les mêmes expressions que les contraintes CHECK de
   decisions-admin-schema.sql : une valeur qui ne passe pas est écartée (champ optionnel) ou
   la ligne est ignorée (numéro de rôle). */
(function(root){
  'use strict';

  var MOIS = { janvier:1, 'février':2, fevrier:2, mars:3, avril:4, mai:5, juin:6, juillet:7,
               'août':8, aout:8, septembre:9, octobre:10, novembre:11, 'décembre':12, decembre:12 };

  var RE_ROLE = /^[0-9]{4,6}[A-Z]{0,2}$/;
  var RE_ECLI = /^ECLI:LU:[A-Z]{2,8}:[0-9]{4}:[A-Za-z0-9]{1,20}$/;
  var RE_URL  = /^https:\/\/ja\.public\.lu\/[A-Za-z0-9_.\/-]{1,150}\.pdf$/;

  function pad(n){ return (n < 10 ? '0' : '') + n; }
  function isoDate(y, m, d){
    var dt = new Date(Date.UTC(y, m - 1, d));
    if(dt.getUTCFullYear() !== y || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
    return y + '-' + pad(m) + '-' + pad(d);
  }
  function fromSlash(s){            /* 30/10/2026 */
    var m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(s);
    return m ? isoDate(+m[3], +m[2], +m[1]) : null;
  }
  function fromFrench(d, mois, y){  /* 30 octobre 2026 */
    var n = MOIS[String(mois).toLowerCase()];
    return n ? isoDate(+y, n, +d) : null;
  }
  function clean(s){ return String(s || '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim(); }

  /* Dossier de 5 000 numéros sur ja.public.lu : 49856 → 45001-50000, 55868 → 55001-60000. */
  function rangeDir(n){ var b = Math.floor((n - 1) / 5000) * 5000; return (b + 1) + '-' + (b + 5000); }

  /* Adresse probable du PDF (le nom de fichier ne garde que les chiffres : 55868R → 55868.pdf).
     Pour les numéros de la Cour (suffixe C) la forme n'est pas vérifiée : null. */
  function probableUrl(role){
    var m = /^([0-9]{4,6})([A-Z]{0,2})$/.exec(String(role || '').toUpperCase());
    if(!m || m[2] === 'C') return null;
    return 'https://ja.public.lu/' + rangeDir(+m[1]) + '/' + m[1] + '.pdf';
  }

  function juridictionOf(text, ecli, role){
    if(/Cour administrative/i.test(text)) return 'Cour administrative';
    if(/Tribunal administratif/i.test(text)) return 'Tribunal administratif';
    if(ecli && /:CADM:/.test(ecli)) return 'Cour administrative';
    if(ecli && /:TADM:/.test(ecli)) return 'Tribunal administratif';
    return /C$/.test(role) ? 'Cour administrative' : 'Tribunal administratif';
  }

  function parseBlock(block, fileNum, fileSuffix, headerDate){
    var m, e = {};
    m = /N°\s*([0-9]{4,6}[A-Z]{0,2})\s+du\s+r[ôo]le/i.exec(block);
    e.role = (m ? m[1] : fileNum + fileSuffix).toUpperCase();
    m = /ECLI:LU:[A-Z]{2,8}:[0-9]{4}:[A-Za-z0-9]{1,20}/.exec(block);
    e.ecli = m ? m[0] : null;
    m = /INSTANCE\s*:\s*(R[ée]f[ée]r[ée]|Tribunal|Cour)/i.exec(block);
    e.instance = m ? (/^r/i.test(m[1]) ? 'Référé' : /^t/i.test(m[1]) ? 'Tribunal' : 'Cour') : null;
    m = /CHAMBRE\s*:\s*([0-9]{1,2})/i.exec(block);
    e.chambre = m ? m[1] : null;
    m = /TYPE DE CONTENTIEUX\s*:\s*([A-Za-zÀ-ÿ' -]{1,60}?)(?=\s*(?:\||INSTANCE|CHAMBRE|$))/i.exec(block);
    e.contentieux = m ? clean(m[1]) : null;
    e.juridiction = juridictionOf(block, e.ecli, e.role);
    m = /Audience publique du\s+(\d{1,2})(?:er)?\s+([A-Za-zéûÉ]+)\s+(\d{4})/i.exec(block);
    e.date = (m && fromFrench(m[1], m[2], m[3])) || headerDate;
    /* Résumé : ce qui suit la date d'audience (le recours et la décision attaquée). */
    var after = m ? block.slice(m.index + m[0].length) : block;
    /* Sans « Audience publique du », on retire au moins les étiquettes de l'en-tête pour ne pas
       les prendre pour un résumé. */
    after = after.replace(/TYPE DE CONTENTIEUX\s*:[^|]*\|?/i, ' ').replace(/INSTANCE\s*:\s*\S+\s*\|?/i, ' ')
                 .replace(/CHAMBRE\s*:\s*[0-9]{1,2}/i, ' ');
    e.resume = clean(after).slice(0, 1500) || null;
    e.url = null;
    e.partial = false;
    return e;
  }

  /* Lit un texte collé. Renvoie { entries: [...], ignored: n } ; chaque entrée :
     { role, ecli, juridiction, instance, chambre, contentieux, date, resume, url, partial }. */
  function parse(raw){
    var text = String(raw || '').replace(/ /g, ' ');
    var byRole = {};
    var ignored = 0;

    /* 1. Adresses de PDF (retirées du texte avant la lecture de la liste) */
    var reUrl = /https?:\/\/ja\.public\.lu\/[0-9]+-[0-9]+\/([0-9]{4,6})([A-Za-z]{0,2})\.pdf/g;
    var um;
    while((um = reUrl.exec(text)) !== null){
      var role = (um[1] + um[2]).toUpperCase();
      var url = 'https://' + um[0].replace(/^https?:\/\//, '');
      if(!RE_ROLE.test(role) || !RE_URL.test(url)){ ignored++; continue; }
      byRole[role] = byRole[role] || { role: role, ecli: null, juridiction: /C$/.test(role) ? 'Cour administrative' : 'Tribunal administratif',
        instance: null, chambre: null, contentieux: null, date: null, resume: null, url: url, partial: true };
      byRole[role].url = url;
    }
    text = text.replace(reUrl, ' ');

    /* 2. Liste copiée : un bloc commence à « 49856.pdf 30/10/2026 » */
    var reHead = /([0-9]{4,6})([A-Z]{0,2})\.pdf\s+([0-9]{2}\/[0-9]{2}\/[0-9]{4})/g;
    var heads = [], hm;
    while((hm = reHead.exec(text)) !== null) heads.push({ idx: hm.index, end: reHead.lastIndex, num: hm[1], suf: hm[2], date: hm[3] });
    heads.forEach(function(h, i){
      var block = text.slice(h.end, i + 1 < heads.length ? heads[i + 1].idx : text.length);
      var e = parseBlock(block, h.num, h.suf, fromSlash(h.date));
      if(!RE_ROLE.test(e.role)){ ignored++; return; }
      var prev = byRole[e.role];
      if(prev && prev.url) e.url = prev.url;
      /* Le nom de fichier ne garde que les chiffres (55868.pdf pour le rôle 55868R) : un lien
         collé sans suffixe se rattache à l'entrée de la liste qui porte ce numéro. */
      var digits = e.role.replace(/[A-Z]+$/, '');
      if(digits !== e.role && byRole[digits] && byRole[digits].partial){
        if(!e.url) e.url = byRole[digits].url;
        delete byRole[digits];
      }
      byRole[e.role] = e;
    });

    /* 3. Validation finale : on écarte ce qui ne passerait pas les contraintes de la base */
    var entries = Object.keys(byRole).map(function(k){
      var e = byRole[k];
      if(e.ecli && !RE_ECLI.test(e.ecli)) e.ecli = null;
      if(e.url && !RE_URL.test(e.url)) e.url = null;
      e.partial = !(e.ecli || e.resume || e.date);
      return e;
    });
    return { entries: entries, ignored: ignored };
  }

  var api = { parse: parse, probableUrl: probableUrl, rangeDir: rangeDir };
  if(typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AdminParse = api;
})(typeof window !== 'undefined' ? window : this);
