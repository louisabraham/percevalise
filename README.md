# percevalise

Un skill pour Claude qui réécrit un texte dans le style de _Perceval le Gallois_ d'Éric Rohmer
(1978) : octosyllabes à rimes plates, français franchement archaïsant, paroles prises dans le récit
avec « fait-il ». Le skill a été construit à partir d'une transcription automatique du film, faite en
local sur un Mac.

| Chemin                                          | Contenu                                                                      |
| ----------------------------------------------- | ---------------------------------------------------------------------------- |
| `skills/percevalise/SKILL.md`                   | le skill                                                                     |
| `sous-titres/Perceval le Gallois (1978).fr.srt` | les sous-titres français (Qwen3-ASR), 1 686 répliques                        |
| `scripts/`                                      | transcription, correction des horodatages, fichier .srt, relevé de fréquence |
| `test/`                                         | le test du skill : passages, réécritures, scripts de mesure                  |

## Utiliser le skill

```sh
cp -r skills/percevalise ~/.claude/skills/
```

Puis, dans Claude Code : « percevalise ce texte : … », ou `/percevalise`.

Exemple tiré du test. En entrée, de la prose moderne :

> Un jeune serviteur sort d'une pièce en tenant une lance blanche par le milieu. Il passe entre la
> cheminée et les gens installés sur le lit. Tout le monde peut voir la lance, blanche, avec sa
> pointe de métal blanc. Une goutte de sang perle au bout de la pointe et descend jusqu'à la main du
> serviteur. Perceval assiste à ce prodige, mais comme il vient d'arriver, il se retient de poser
> la moindre question.

En sortie (les 14 premiers vers) :

> Un jeune serviteur alors\
> D'une chambre est issu dehors,\
> Une lance blanche tenant\
> Par le milieu, et va passant\
> Entre le feu, comme je dis,\
> Et ceux qui séaient sur le lit.\
> Tous virent lance blanche et blanc\
> Le fer ; au bout, goutte de sang\
> Perle, et coule tant qu'elle vient\
> Jusqu'à la main qui la soutient.\
> Perceval voit cette merveille\
> Dont ne vit onques la pareille ;\
> Mais, comme il est nouveau venu,\
> De rien demander s'est tenu.

## Étape 1 : transcrire le film

Tout a tourné en local, sur un Mac M4 Max, avec des modèles au format MLX. Le film dure 2 h 20.

### Extraire la piste audio

```sh
ffmpeg -i film.mkv -map 0:a:0 -ac 1 -ar 16000 film.wav
```

### Comparer trois modèles

| Modèle                                | Durée  | Mots confirmés par un autre modèle | Sur les passages chantés         |
| ------------------------------------- | ------ | ---------------------------------- | -------------------------------- |
| Parakeet TDT 0.6B v3 (`parakeet-mlx`) | 3 min  | 88,7 %                             | faible                           |
| Whisper large-v3 (`mlx-whisper`)      | 20 min | 78,9 %                             | saute des vers entiers (« ... ») |
| **Qwen3-ASR 1.7B** (`mlx-audio`)      | 6 min  | **89,6 %**                         | **le meilleur**                  |

Il n'existe pas de transcription de référence. La colonne du milieu mesure donc l'accord entre
modèles : la part des mots d'un modèle qu'au moins un des deux autres a aussi entendus
(`scripts/agree.py`). C'est un indice, pas une mesure d'exactitude.

Le dialogue parlé sort bien chez les trois. La différence se fait sur la narration chantée par le
chœur, en vers archaïsants. Le début du film, comparé au texte de Chrétien de Troyes :

| Chrétien (vers d'origine)          | Parakeet                         | Qwen3-ASR                            |
| ---------------------------------- | -------------------------------- | ------------------------------------ |
| Ce fu au tans qu'arbre foillissent | Ce fut tout en carbre feuillisse | Ce fut autant qu'arbres feuillissent |
| que glai et bois et pré verdissent | herbeuse et boire et préverdisse | herbes et bois et prés verdissent    |
| que li filz a la veve dame         | que le fils de la œuvre d'homme  | que le fils de la veuve dame         |
| … trois javeloz                    | qui ne prie trois charges d'eau  | qui ne prit trois javelots           |

Commandes pour les deux autres modèles :

```sh
uvx parakeet-mlx film.wav --output-format json
uvx --from mlx-whisper mlx_whisper film.wav --model mlx-community/whisper-large-v3-mlx \
    --language fr --output-format json --word-timestamps True \
    --condition-on-previous-text False --hallucination-silence-threshold 2
```

### Les pièges de Qwen3-ASR, et les garde-fous

Qwen3-ASR ne donne pas l'horodatage des mots. Son compagnon, Qwen3-ForcedAligner, le calcule à partir
du texte et de l'audio. Le film est découpé en morceaux d'une minute, coupés sur des silences.
Trois problèmes sont apparus au premier passage :

1. **Boucles.** Sur deux morceaux chantés, le modèle a répété « ah ah ah… » ou « oui, oui… »
   jusqu'à 8 192 jetons. Le script limite le nombre de jetons à la durée du morceau ; si le texte
   boucle quand même, il refait le morceau en tranches de 20 s avec une pénalité de répétition.
2. **Contexte recraché.** Le modèle reçoit un court contexte (noms propres, vocabulaire médiéval).
   Sur la fin silencieuse du film, il a recopié ce contexte mot pour mot. Le script le détecte et
   refait le morceau sans contexte. Le contexte n'a d'ailleurs presque rien changé au résultat.
3. **Mots étirés.** L'aligneur étale parfois un mot sur une longue pause (« Arthur » sur 10,8 s) et
   écrase les suivants à une durée nulle. Pour ces mots-là seulement, `fix_times.py` reprend
   l'horodatage du même mot chez Parakeet (71 mots), ou répartit le temps entre les voisins fiables
   (151 mots).

```sh
uvx --from mlx-audio python -I scripts/qwen_transcribe.py film.wav qwen.json
python3 scripts/fix_times.py qwen.json parakeet.json qwen_fixed.json
python3 scripts/words_to_srt.py qwen_fixed.json film.fr.srt
```

### Découper en répliques

Le découpage fourni par `parakeet-mlx` coupait des mots en deux (« d » / « 'homme »). Les répliques
sont donc reconstruites à partir de l'horodatage des mots (`words_to_srt.py`) :

- une nouvelle réplique après une fin de phrase, ou après une pause de plus d'une seconde (trois
  secondes au milieu d'un vers chanté) ;
- au plus 6,5 s et deux lignes de 42 caractères ;
- dans les passages chantés, Qwen met une majuscule au début de chaque vers : chaque vers devient
  une réplique ;
- le texte reste affiché 0,6 s après la fin de la parole, sans chevaucher la réplique suivante.

### Limites

- La Passion chantée en latin (de 2:09 à 2:17) est illisible : aucun des trois modèles ne
  reconnaît le latin.
- Des noms sont mal entendus (Keu devient « Quê », Clamadeu « Clavadière »), ainsi que des mots
  anciens (« mout » pour moult, « aubert » pour haubert, « oxir » pour occire).
- Dans quelques vers chantés très lents, l'horodatage reste approximatif.

## Étape 2 : du sous-titre au skill

### Lire tout le texte

Le fichier de sous-titres a été lu en entier, en séparant deux choses : les archaïsmes, voulus par
Rohmer, et les erreurs de reconnaissance. Cinq traits reviennent tout au long du film, et le skill
est organisé autour d'eux :

1. des octosyllabes à rimes plates, où une rime peut passer d'une réplique à la réponse ;
2. des paroles prises dans le récit, avec « fait-il », et un narrateur qui intervient (« Que vous
   dirais-je ? ») ;
3. des répétitions et des refrains (« Le chevalier sans nul arrêt / Va chevauchant par la
   forêt ») ;
4. une langue archaïsante : inversions (« Chevalier suis »), négation sans « pas », passé simple,
   subjonctif imparfait, vocatifs (« beau doux ami »), serments (« par ma foi ») ;
5. un ton naïf et pince-sans-rire, avec des maximes (« Ce qu'on ne sait, on peut l'apprendre / Si
   l'on veut peiner et entendre »).

Chaque vers cité dans le skill a été corrigé des erreurs de reconnaissance, puis compté à huit
syllabes. Ce comptage a corrigé une règle : le film compte le e de « montée » ou « empoignée » devant
une consonne (« À la mon·té·e des degrés »).

### Qui répète ?

Les sous-titres ne disent pas qui parle. Pour savoir si les répétitions viennent de Perceval ou des
chanteurs, deux mesures ont été faites sur l'audio de chaque répétition :

- la part de notes tenues (hauteur stable pendant au moins 150 ms), qui sépare le chant de la
  parole ;
- la ressemblance de voix (modèle ECAPA), calibrée sur des répliques sûres de Perceval, de sa mère
  et des chanteurs : 16 répliques sur 17 bien attribuées, même coupées à 0,6 s.

Résultat : Perceval reprend en écho le mot de l'autre (« le surplus je vous le défends. — Le
baiser. », « n'ayez peur. — Peur ? ») et redit son salut quand le roi ne répond pas. Les vers entiers
repris (« Jamais je ne vous oublierai », « Qui trop parle péché fait ») sont surtout chantés : la
phrase d'un personnage revient en refrain. Le skill distingue ces trois formes dans sa section 3.4.

### Compter les mots du film

`scripts/frequencies.py` compare la fréquence de chaque mot du film à sa fréquence en français
courant (paquet `wordfreq`). Quelques résultats, sur environ 12 000 mots :

| Mot        | Occurrences | Fréquence par rapport au français moderne |
| ---------- | ----------- | ----------------------------------------- |
| occire     | 9           | ×4 700                                    |
| pucelle(s) | 37          | ×2 200 à ×4 100                           |
| moult      | 21          | ×950                                      |
| sire       | 68          | ×930                                      |
| vint       | 8           | ×120                                      |
| nul        | 16          | ×22                                       |
| ni         | 56          | ×15                                       |
| car        | 54          | ×9                                        |

Le relevé a surpris : les archaïsmes rares (« lors », « mie », « onc », « céans ») apparaissent à
peine. Le son du film vient surtout de mots courants employés à l'ancienne (car, ni, nul, tant,
si), du passé simple et des formules d'adresse. Ces listes, avec un tableau de remplacements (très
→ moult, tuer → occire, parce que → car, jeune fille → pucelle), forment la section 4.4 du skill.

```sh
uvx --with wordfreq python -I scripts/frequencies.py "sous-titres/Perceval le Gallois (1978).fr.srt"
```

### Tester le skill

Le test vérifie si un agent qui suit le skill retrouve le style du film :

1. Quatre passages du film (48 vers) ont été choisis parmi ceux que le skill ne cite pas.
2. Chaque passage a été réécrit en prose moderne (`test/plains.json`).
3. Des agents Claude ont remis cette prose « dans le style de Perceval le Gallois », avec et sans le
   skill, deux fois chacun.
4. Les réécritures (`test/sorties/`) ont été comparées aux vers d'origine (`test/originals.json`).

Le compteur de syllabes de `test/score.py` suit les règles du skill. Il trouve huit syllabes dans
les 48 vers d'origine, et compte juste 9 vers connus sur 11 (alexandrins, hexasyllabes).

| Version          | Vers de 8 syllabes | chrF avec l'original | Mots du film pour 100 mots |
| ---------------- | ------------------ | -------------------- | -------------------------- |
| sans skill       | 89 %, 96 %         | 53,3 ; 58,7          | 1,3 ; 1,0                  |
| skill, version 1 | 100 %, 98 %        | 54,1 ; 53,9          | 1,6 ; 1,7                  |
| skill, version 2 | 98 %, 96 %         | 57,0 ; 53,8          | 3,6 ; 4,1                  |
| film entier      |                    |                      | 4,7                        |

- Le skill améliore la métrique : les vers faux passent de 7 sur 94 à 1 sur 96 (version 1).
- Avec la section de fréquence (version 2), la densité de mots du film passe de 1 à environ 4 pour
  100 mots, près de celle du film (4,7).
- Le skill ne rapproche pas la réécriture du texte exact de Rohmer : sans skill, Claude connaît déjà
  assez Chrétien de Troyes pour retrouver certains vers. Avec deux essais par version, ces écarts
  restent dans le bruit.

```sh
cd test
python3 score.py originals.json plains.json sorties/*.txt
python3 density.py sorties/*.txt
```

## Droits

Le texte du film est la traduction de Chrétien de Troyes par Éric Rohmer (Les Films du Losange,
1978). Les sous-titres sont une transcription automatique faite pour l'étude du style ; ils
contiennent des erreurs.
