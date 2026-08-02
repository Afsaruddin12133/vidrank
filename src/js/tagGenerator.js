// YouTube Auto Tag Generator - Offline SEO Engine

const TagGenerator = {
  // Common prepositions, articles, and auxiliary words to filter out
  STOP_WORDS: new Set([
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are', 'arent', 'as', 'at',
    'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'by', 'cant', 'cannot', 'could',
    'couldnt', 'did', 'didnt', 'do', 'does', 'doesnt', 'doing', 'dont', 'down', 'during', 'each', 'few', 'for', 'from',
    'further', 'had', 'hadnt', 'has', 'hasnt', 'have', 'havent', 'having', 'he', 'hed', 'hell', 'hes', 'her', 'here',
    'heres', 'hers', 'herself', 'him', 'himself', 'his', 'how', 'hows', 'i', 'id', 'ill', 'im', 'ive', 'if', 'in', 'into',
    'is', 'isnt', 'it', 'its', 'itself', 'lets', 'me', 'more', 'most', 'mustnt', 'my', 'myself', 'no', 'nor', 'not', 'of',
    'off', 'on', 'once', 'only', 'or', 'other', 'ought', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', 'shant',
    'she', 'shed', 'shell', 'shes', 'should', 'shouldnt', 'so', 'some', 'such', 'than', 'that', 'thats', 'the', 'their',
    'theirs', 'them', 'themselves', 'then', 'there', 'theres', 'these', 'they', 'theyd', 'theyll', 'theyre', 'theyve',
    'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up', 'very', 'was', 'wasnt', 'we', 'wed', 'well', 'were',
    'weve', 'werent', 'what', 'whats', 'when', 'whens', 'where', 'wheres', 'which', 'while', 'who', 'whos', 'whom',
    'why', 'whys', 'with', 'wont', 'would', 'wouldnt', 'you', 'youd', 'youll', 'youre', 'youve', 'your', 'yours',
    'yourself', 'yourselves', 'in', 'on', 'at', 'to', 'for', 'by', 'with', 'from', 'up', 'about', 'into', 'over', 'after',
    'the', 'a', 'an', 'and', 'but', 'or', 'nor', 'for', 'yet', 'so'
  ]),

  // Common location terms for geographic targeting
  LOCATIONS: [
    'bangladesh', 'bd', 'india', 'pakistan', 'usa', 'uk', 'united kingdom', 'america', 'canada', 
    'australia', 'nigeria', 'philippines', 'germany', 'france', 'london', 'dhaka', 'delhi', 'new york'
  ],

  // Structured category keywords & related tags thesaurus
  CATEGORIES: {
    finance: {
      triggers: ['earn', 'money', 'income', 'cash', 'passive', 'rich', 'dollar', 'crypto', 'bitcoin', 'business', 'freelance', 'freelancing', 'job', 'jobs', 'salary', 'invest', 'investment', 'profit', 'hustle', 'finance'],
      tags: [
        'earn money online', 'make money online', 'passive income', 'online business', 
        'work from home', 'side hustle', 'make money from home', 'how to make money', 
        'financial freedom', 'extra income', 'online earning', 'earn money', 'freelancing', 
        'internet income', 'online jobs', 'earning tips', 'work online', 'make money'
      ]
    },
    tech: {
      triggers: ['tech', 'technology', 'code', 'coding', 'programming', 'software', 'app', 'apps', 'review', 'unboxing', 'smartphone', 'iphone', 'android', 'computer', 'laptop', 'ai', 'artificial intelligence', 'gadget', 'windows', 'mac', 'developer'],
      tags: [
        'tech review', 'gadget unboxing', 'new technology', 'software tutorial', 
        'coding for beginners', 'programming guide', 'tech tips', 'unboxing video', 
        'app review', 'latest gadgets', 'ai tutorial', 'artificial intelligence tech',
        'tech channel', 'technology news', 'how to code', 'software development'
      ]
    },
    gaming: {
      triggers: ['game', 'gaming', 'play', 'walkthrough', 'gameplay', 'stream', 'live', 'fortnite', 'minecraft', 'roblox', 'pubg', 'apex', 'cod', 'xbox', 'ps5', 'nintendo', 'gamer', 'mobile game', 'free fire'],
      tags: [
        'gaming channel', 'gameplay', 'walkthrough', 'let\'s play', 'gaming video', 
        'game review', 'new games', 'live stream', 'gaming community', 'pro gameplay', 
        'console gaming', 'pc gaming', 'mobile gaming', 'gaming tips', 'funny gaming moments'
      ]
    },
    education: {
      triggers: ['how to', 'tutorial', 'guide', 'learn', 'course', 'education', 'tips', 'step by step', 'for beginners', 'school', 'study', 'teach', 'class', 'tricks', 'explained', 'science', 'history'],
      tags: [
        'step by step tutorial', 'how to tutorial', 'for beginners', 'complete guide', 
        'tips and tricks', 'learn online', 'step by step guide', 'how to', 'tutorial', 
        'easy tutorial', 'educational video', 'study tips', 'explainer video', 'learning'
      ]
    },
    lifestyle: {
      triggers: ['vlog', 'vlogs', 'travel', 'trip', 'explore', 'tour', 'adventure', 'daily', 'life', 'routine', 'lifestyle', 'family', 'vlogger', 'challenge', 'couples'],
      tags: [
        'daily vlog', 'travel vlog', 'vlogger', 'lifestyle vlog', 'day in the life', 
        'travel guide', 'vlog video', 'life updates', 'travel adventure', 'family vlog',
        'lifestyle video', 'daily routine', 'fun challenges'
      ]
    },
    food: {
      triggers: ['food', 'cooking', 'recipe', 'chef', 'eat', 'eating', 'restaurant', 'kitchen', 'bake', 'baking', 'delicious', 'taste', 'meal', 'street food', 'dessert', 'dinner', 'breakfast'],
      tags: [
        'cooking recipe', 'how to cook', 'food review', 'street food', 'easy recipe', 
        'cooking tutorial', 'healthy food', 'kitchen tips', 'quick meals', 'baking recipe',
        'food vlog', 'how to bake', 'delicious dishes', 'homemade recipe'
      ]
    },
    fitness: {
      triggers: ['workout', 'fitness', 'gym', 'health', 'exercise', 'weight loss', 'diet', 'lose weight', 'cardio', 'muscle', 'nutrition', 'bodybuilding', 'healthy', 'yoga', 'stretch'],
      tags: [
        'workout routine', 'fitness tips', 'weight loss journey', 'gym motivation', 
        'home workout', 'healthy diet', 'exercise at home', 'lose weight', 'health tips', 
        'fitness goals', 'bodybuilding guide', 'home exercise', 'muscle building', 'cardio workout'
      ]
    },
    music: {
      triggers: ['music', 'song', 'remix', 'beat', 'cover', 'instrumental', 'lyrics', 'sing', 'singer', 'playlist', 'lofi', 'rap', 'hiphop', 'acoustic', 'guitar', 'piano'],
      tags: [
        'music video', 'new song', 'lyric video', 'instrumental beat', 'song cover', 
        'relaxing music', 'background music', 'remix song', 'lofi beats', 'acoustic cover', 
        'singer songwriter', 'music playlist', 'instrumental cover'
      ]
    }
  },

  /**
   * Generates highly relevant tags from a video title.
   * @param {string} title - The video title.
   * @param {Object} options - Custom parameters.
   * @param {number} options.maxCount - Max number of tags (default: 35).
   * @returns {string[]} An array of tags.
   */
  generate: function(title, options = {}) {
    const maxCount = options.maxCount || 35;
    if (!title || typeof title !== 'string' || !title.trim()) {
      return [];
    }

    const cleanTitle = title.toLowerCase().trim();
    
    // 1. Clean Title and parse tokens
    // Replace typical delimiters with spaces
    const normalizedTitle = cleanTitle
      .replace(/[|\[\](){}:;,\-\/\\&?!\u2013\u2014._+*=#]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    const words = normalizedTitle.split(' ').filter(w => w.length > 0);
    const keywords = words.filter(w => !this.STOP_WORDS.has(w));

    // Detect Year if present
    const yearMatch = title.match(/\b(202[4-9]|203[0-5])\b/);
    const detectedYear = yearMatch ? yearMatch[0] : null;

    // Detect Location if present
    let detectedLocation = null;
    for (const loc of this.LOCATIONS) {
      if (normalizedTitle.includes(loc)) {
        detectedLocation = loc;
        break;
      }
    }

    // Set of unique tags to accumulate
    const tagsSet = new Set();

    // 2. Exact Title Tag (if length is reasonable)
    if (normalizedTitle.length > 3 && normalizedTitle.length < 80) {
      tagsSet.add(normalizedTitle);
    }
    
    // Add original title minus symbols (up to 100 chars)
    if (normalizedTitle.length > 0 && normalizedTitle !== cleanTitle && cleanTitle.length < 100) {
      tagsSet.add(cleanTitle.replace(/[|\[\](){}:;,\-\/\\&?!\u2013\u2014._+*=#]/g, '').replace(/\s+/g, ' ').trim());
    }

    // 3. Category Detection and Thesaurus Loading
    let detectedCategories = [];
    for (const [catName, catData] of Object.entries(this.CATEGORIES)) {
      const isMatched = catData.triggers.some(trigger => {
        // Full word match or substring if trigger is short
        return words.includes(trigger) || (trigger.length > 4 && normalizedTitle.includes(trigger));
      });
      if (isMatched) {
        detectedCategories.push(catName);
      }
    }

    // 4. Generate Keyphrases (N-Grams of words)
    // Extract contiguous phrases of 2, 3, and 4 words
    const phraseTiers = [2, 3, 4];
    const generatedPhrases = [];
    
    phraseTiers.forEach(tier => {
      for (let i = 0; i <= words.length - tier; i++) {
        const slice = words.slice(i, i + tier);
        // Skip phrase if all words are stopwords, or if it begins/ends with minor words
        const startsWithStop = this.STOP_WORDS.has(slice[0]);
        const endsWithStop = this.STOP_WORDS.has(slice[slice.length - 1]);
        
        // We allow some stop words if the phrase has keywords
        const containsKeyword = slice.some(w => !this.STOP_WORDS.has(w));
        
        if (containsKeyword) {
          const phraseStr = slice.join(' ');
          // Avoid tiny/weird phrases
          if (phraseStr.length > 4) {
            generatedPhrases.push(phraseStr);
          }
        }
      }
    });

    // Add generated keyphrases to tagSet in order of length (longer phrases first)
    generatedPhrases.sort((a, b) => b.split(' ').length - a.split(' ').length);
    generatedPhrases.forEach(p => tagsSet.add(p));

    // 5. Build Year & Location customized phrase variations (High value SEO)
    const contextPhrases = [];
    if (detectedYear || detectedLocation) {
      // Create variations of keywords & short keyphrases
      const shortPhrases = generatedPhrases.filter(p => p.split(' ').length <= 3);
      
      shortPhrases.forEach(phrase => {
        if (detectedLocation && !phrase.includes(detectedLocation)) {
          contextPhrases.push(`${phrase} ${detectedLocation}`);
          contextPhrases.push(`${detectedLocation} ${phrase}`);
        }
        if (detectedYear && !phrase.includes(detectedYear)) {
          contextPhrases.push(`${phrase} ${detectedYear}`);
        }
        if (detectedLocation && detectedYear && !phrase.includes(detectedLocation) && !phrase.includes(detectedYear)) {
          contextPhrases.push(`${phrase} ${detectedLocation} ${detectedYear}`);
        }
      });
    }
    contextPhrases.forEach(p => tagsSet.add(p));

    // 6. Append Category Specific Tags (incorporating geographic/temporal filters)
    detectedCategories.forEach(catName => {
      const catTags = this.CATEGORIES[catName].tags;
      
      // First add the raw category tags
      catTags.forEach(tag => tagsSet.add(tag));
      
      // Add geography and year localized variants of the category tags
      catTags.slice(0, 8).forEach(tag => {
        if (detectedLocation && !tag.includes(detectedLocation)) {
          tagsSet.add(`${tag} ${detectedLocation}`);
        }
        if (detectedYear && !tag.includes(detectedYear)) {
          tagsSet.add(`${tag} ${detectedYear}`);
        }
        if (detectedLocation && detectedYear && !tag.includes(detectedLocation) && !tag.includes(detectedYear)) {
          tagsSet.add(`${tag} ${detectedLocation} ${detectedYear}`);
        }
      });
    });

    // 7. Add Individual Keywords (only nouns/verbs, no stop words)
    keywords.forEach(keyword => {
      if (keyword.length > 2) {
        tagsSet.add(keyword);
      }
    });

    // Fallback: If title was extremely short and we don't have enough tags, add generic tags
    if (tagsSet.size < 10) {
      const fallbacks = ['tutorial', 'video', 'youtube video', 'guide', 'tips', 'tricks', 'howto', 'vlog', 'review'];
      fallbacks.forEach(tag => tagsSet.add(tag));
    }

    // 8. Convert to Array, clean whitespace, deduplicate and prioritize
    let finalTagsList = Array.from(tagsSet)
      .map(tag => tag.toLowerCase().replace(/\s+/g, ' ').trim())
      .filter(tag => {
        // Tag validation (YouTube tags can be up to 100 characters each)
        return tag.length >= 2 && tag.length <= 80 && !/^\d+$/.test(tag); // Avoid raw years or numbers as isolated tags if possible
      });

    // Remove duplicates
    finalTagsList = [...new Set(finalTagsList)];

    // 9. Check cumulative character constraints
    // YouTube allows up to 500 characters including commas
    const selectedTags = [];
    let currentLength = 0;

    for (const tag of finalTagsList) {
      if (selectedTags.length >= maxCount) break;
      
      // Comma separator character count cost: tag length + 1 (for comma)
      const cost = tag.length + 1;
      if (currentLength + cost <= 475) { // 475 is a safe ceiling under 500 limit
        selectedTags.push(tag);
        currentLength += cost;
      }
    }

    return selectedTags;
  },

  /**
   * Formats a list of tags as hashtags.
   * @param {string[]} tags - The tags list.
   * @returns {string[]} An array of hashtags.
   */
  toHashtags: function(tags) {
    if (!tags || !Array.isArray(tags)) return [];
    return tags.map(tag => {
      // Remove spaces and special characters, prepend #
      const cleaned = tag.replace(/[^a-zA-Z0-9\u0980-\u09FF]/g, '').toLowerCase(); // allow alphanumeric and bengali characters, strip spaces/punctuations
      return cleaned.startsWith('#') ? cleaned : '#' + cleaned;
    }).filter(t => t.length > 1); // skip empty / single # symbol chips
  }
};

// Export to window if running in browser
if (typeof window !== 'undefined') {
  window.TagGenerator = TagGenerator;
}

// Export as module if running in Node (for unit testing or scripts)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = TagGenerator;
}
