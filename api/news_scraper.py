"""
News scraper for emissions-related news.
"""
import requests
import logging
from typing import List, Dict, Optional
from django.conf import settings
from datetime import datetime, timedelta
import feedparser
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)


class NewsScraper:
    """Scrapes news related to emissions and CO2 data."""
    
    def __init__(self):
        """Initialize the news scraper."""
        # Read NEWS_API_KEY safely; allow None when not configured
        self.news_api_key = getattr(settings, 'NEWS_API_KEY', None)
        self.credible_sources = [
            'bbc.com',
            'reuters.com',
            'theguardian.com',
            'nytimes.com',
            'washingtonpost.com',
            'climate.gov',
            'ipcc.ch',
            'un.org',
            'worldbank.org',
            'iea.org',
            'carbonbrief.org',
            'scientificamerican.com',
            'nature.com',
            'science.org'
        ]
        # optional spaCy NLP model for better noun-chunk extraction
        self._nlp = None
        try:
            import spacy
            try:
                # prefer small English model; may not be installed
                self._nlp = spacy.load('en_core_web_sm')
            except Exception:
                # fallback to blank English pipeline if small model missing
                self._nlp = spacy.blank('en')
        except Exception:
            self._nlp = None
    
    def scrape_news(self, query_keywords: str, max_results: int = 5) -> List[Dict]:
        """
        Scrape news articles related to the query keywords.
        
        Args:
            query_keywords: Keywords extracted from user query
            max_results: Maximum number of articles to return
            
        Returns:
            List of news article dictionaries
        """
        logger.debug("scrape_news start: query=%s max_results=%s", query_keywords, max_results)
        # Aggregate from multiple sources (NewsAPI, RSS, search) into raw list
        raw_articles: List[Dict] = []

        # Try NewsAPI first if available
        if self.news_api_key:
            try:
                nas = self._fetch_from_newsapi(query_keywords, max_results)
                logger.debug("newsapi returned %d articles", len(nas))
                raw_articles.extend(nas)
            except Exception as e:
                logger.error(f"NewsAPI fetch failed: {str(e)}")

        # RSS feeds
        try:
            rrs = self._fetch_from_rss(query_keywords, max_results)
            logger.debug("rss fetch returned %d articles", len(rrs))
            raw_articles.extend(rrs)
        except Exception as e:
            logger.error(f"RSS fetch failed: {str(e)}")

        # If still lacking, use search scraping as a last resort
        try:
            rcs = self._fetch_from_search(query_keywords, max_results * 2)
            logger.debug("search fetch returned %d articles", len(rcs))
            raw_articles.extend(rcs)
        except Exception as e:
            logger.error(f"search fetch failed: {str(e)}")

        # Rank and deduplicate aggregated results
        ranked = self._rank_and_dedupe_articles(raw_articles, query_keywords, max_results)
        return ranked

    def _rank_and_dedupe_articles(self, articles: List[Dict], query: str, max_results: int) -> List[Dict]:
        """
        Rank articles by token overlap with query, boost credible sources, and prefer recent items.
        Also deduplicate by URL.
        """
        if not articles:
            return []

        # compute focus tokens from query (use spacy if available)
        focus_str = self._extract_search_terms(query)
        logger.debug("ranking: query=%s focus_terms=%s total_raw_articles=%d", query, focus_str, len(articles))
        focus_tokens = set([t.lower() for t in focus_str.split() if len(t) > 1])

        scored = []
        seen = set()
        now = datetime.utcnow()

        for a in articles:
            url = (a.get('url') or a.get('link') or '').strip()
            if not url or url in seen:
                continue
            seen.add(url)

            title = (a.get('title') or '').lower()
            desc = (a.get('description') or a.get('summary') or '').lower()
            text_blob = f"{title} {desc} {url}".lower()

            # token overlap score — count exact token matches in title and description
            overlap = 0
            for t in focus_tokens:
                if t in (title or ''):
                    overlap += 2
                if t in (desc or ''):
                    overlap += 1

            # credible source boost
            src = (a.get('source') or '')
            credible_boost = 1.0
            try:
                domain = self._extract_domain(url)
                if any(c in domain for c in self.credible_sources):
                    credible_boost = 1.5
            except Exception:
                credible_boost = 1.0

            # recency bonus (if published_at parseable)
            recency = 0.0
            pub = a.get('published_at') or a.get('pubDate') or a.get('published') or ''
            if pub:
                try:
                    dt = dateparser.parse(pub)
                    if isinstance(dt, datetime):
                        days = max((now - dt).days, 0)
                        # recent articles get a small bonus inversely proportional to age
                        recency = max(0, 7 - min(days, 30)) / 7.0
                except Exception:
                    recency = 0.0

            # increase overlap importance to favor focused matches
            score = (overlap * 3.0 + recency) * credible_boost

            scored.append((score, overlap, credible_boost, recency, a))

        # sort by score desc, then overlap desc
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        # Log top candidates for debugging
        top_debug = []
        for s in scored[: max_results * 2]:
            sc, ov, cb, rc, art = s
            top_debug.append({
                'score': sc,
                'overlap': ov,
                'credible_boost': cb,
                'recency': rc,
                'title': (art.get('title') or '')[:120],
                'url': art.get('url') or art.get('link') or ''
            })
        logger.debug("ranking top candidates: %s", top_debug)

        results = [item[-1] for item in scored][:max_results]
        logger.debug("ranking returning %d articles", len(results))
        return results
    
    def _fetch_from_newsapi(self, query: str, max_results: int) -> List[Dict]:
        """Fetch news from NewsAPI."""
        try:
            # Extract key terms from query
            search_terms = self._extract_search_terms(query)
            logger.debug("newsapi: search_terms=%s max_results=%d", search_terms, max_results)
            
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': search_terms,
                'language': 'en',
                'sortBy': 'relevancy',
                'pageSize': max_results,
                'from': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                'apiKey': self.news_api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            articles = []
            
            for article in data.get('articles', []):
                # Filter by credible sources
                source_domain = self._extract_domain(article.get('url', ''))
                if any(credible in source_domain for credible in self.credible_sources):
                    articles.append({
                        'title': article.get('title', ''),
                        'description': article.get('description', ''),
                        'url': article.get('url', ''),
                        'source': article.get('source', {}).get('name', ''),
                        'published_at': article.get('publishedAt', ''),
                        'image_url': article.get('urlToImage', '')
                    })
            
            return articles
            
        except Exception as e:
            logger.error(f"NewsAPI error: {str(e)}")
            return []
    
    def _fetch_from_rss(self, query: str, max_results: int) -> List[Dict]:
        """Fetch news from RSS feeds."""
        articles = []
        
        # RSS feeds for climate/emissions news
        rss_feeds = [
            'https://feeds.bbci.co.uk/news/science_and_environment/rss.xml',
            'https://www.theguardian.com/environment/climate-change/rss',
            'https://rss.cnn.com/rss/edition.rss',  # General news, filter by keywords
        ]
        
        search_terms = self._extract_search_terms(query)
        search_terms_lower = [term.lower() for term in search_terms.split()]
        logger.debug("rss: search_terms=%s max_results=%d feeds=%d", search_terms, max_results, len(rss_feeds))
        
        for feed_url in rss_feeds:
            try:
                feed = feedparser.parse(feed_url)
                logger.debug("rss: parsed feed %s entries=%d", feed_url, len(feed.entries))
                
                for entry in feed.entries[:10]:  # Check first 10 entries
                    if len(articles) >= max_results:
                        break
                    
                    title = entry.get('title', '')
                    summary = entry.get('summary', '')
                    content = (title + ' ' + summary).lower()
                    
                    # Check if entry is relevant
                    if any(term in content for term in search_terms_lower):
                        articles.append({
                            'title': title,
                            'description': summary[:200] + '...' if len(summary) > 200 else summary,
                            'url': entry.get('link', ''),
                            'source': feed.feed.get('title', 'RSS Feed'),
                            'published_at': entry.get('published', ''),
                            'image_url': ''
                        })
                
                if len(articles) >= max_results:
                    break
                    
            except Exception as e:
                logger.error(f"RSS feed error for {feed_url}: {str(e)}")
                continue
        
        return articles

    def _fetch_from_search(self, query: str, max_results: int) -> List[Dict]:
        """Fetch news by performing an HTML search (DuckDuckGo) and scraping result pages."""
        articles = []
        try:
            # Prefer Google News RSS first (more targeted news results)
            from urllib.parse import quote_plus
            search_terms = self._extract_search_terms(query) or query
            google_q = quote_plus(search_terms)
            google_rss = f'https://news.google.com/rss/search?q={google_q}&hl=en-US&gl=US&ceid=US:en'
            logger.debug("search: trying Google News RSS url=%s max_results=%d", google_rss, max_results)
            feed = feedparser.parse(google_rss)
            if feed and getattr(feed, 'entries', None):
                logger.debug("search: google news rss entries=%d", len(feed.entries))
                for entry in feed.entries[:max_results]:
                    title = entry.get('title', '')
                    summary = entry.get('summary', '')
                    link = entry.get('link', '')
                    pub = entry.get('published', '') or entry.get('pubDate', '')
                    try:
                        from urllib.parse import urlparse
                        source = urlparse(link).netloc.replace('www.', '')
                    except Exception:
                        source = ''
                    articles.append({
                        'title': title,
                        'description': summary[:200] + '...' if len(summary) > 200 else summary,
                        'url': link,
                        'source': source,
                        'published_at': pub,
                        'image_url': ''
                    })
                logger.debug("search: returning %d google-rss articles", len(articles))
                return articles[:max_results]

            # If Google RSS returned nothing, fallback to DuckDuckGo HTML scraping
            logger.debug("search: Google News RSS returned no entries, falling back to DuckDuckGo")
            # Prefer credible sources in the search query to improve relevance
            search_url = 'https://html.duckduckgo.com/html/'
            # Build site-limited query using top credible sources to bias results
            site_terms = ' '.join([f"site:{d}" for d in self.credible_sources[:8]])
            final_query = f"{query} {site_terms}"
            params = {'q': final_query}
            logger.debug("search: final_query=%s max_results=%d", final_query, max_results)
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; CarbonLens/1.0)'}
            resp = requests.get(search_url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')

            # Prefer result anchors specific to DuckDuckGo HTML output
            links = []
            anchors = soup.select('a.result__a') or soup.select('a[data-testid="result-title-a"]')
            if not anchors:
                anchors = soup.find_all('a')
            logger.debug("search: anchors_found=%d", len(anchors))

            for a in anchors:
                try:
                    href = a.get('href') or ''
                    txt = (a.get_text() or '').strip()
                    if href and txt and href.startswith('http'):
                        links.append((txt, href))
                except Exception:
                    continue

            # Visit top links and extract title/description
            # filter links by presence of query tokens in title/snippet to improve relevance
            query_tokens = [t.lower() for t in self._extract_search_terms(query).split() if len(t) > 2]
            logger.debug("search: query_tokens=%s", query_tokens)
            for title_text, url in links:
                if len(articles) >= max_results:
                    break
                try:
                    p = requests.get(url, headers=headers, timeout=8)
                    p.raise_for_status()
                    page = BeautifulSoup(p.text, 'html.parser')
                    # Get meta description
                    desc = ''
                    md = page.find('meta', attrs={'name': 'description'}) or page.find('meta', attrs={'property': 'og:description'})
                    if md and md.get('content'):
                        desc = md.get('content')
                    # Get site title/source
                    source = ''
                    try:
                        from urllib.parse import urlparse
                        source = urlparse(url).netloc.replace('www.', '')
                    except Exception:
                        source = ''

                    # Relevance check: ensure at least one token appears in title or description
                    text_blob = (title_text + ' ' + (desc or '')).lower()
                    if query_tokens and not any(tok in text_blob for tok in query_tokens):
                        # skip less relevant result
                        continue

                    articles.append({
                        'title': title_text,
                        'description': (desc[:200] + '...') if desc and len(desc) > 200 else desc,
                        'url': url,
                        'source': source,
                        'published_at': '',
                        'image_url': ''
                    })
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"search fetch failed: {e}")

        return articles
    
    def _extract_search_terms(self, query: str) -> str:
        """Extract relevant search terms from query."""
        import re

        q = (query or '').strip()
        if not q:
            return ''

        # If spaCy is available, use noun-chunking and named-entity extraction for precise keywords
        if self._nlp is not None:
            try:
                doc = self._nlp(q)
                # collect noun chunks
                noun_chunks = [chunk.text.strip() for chunk in doc.noun_chunks if len(chunk.text.strip()) > 2]
                # collect named entities of interest (GPE: countries/cities, ORG)
                ents = [ent.text.strip() for ent in doc.ents if ent.label_ in ('GPE', 'LOC', 'ORG') and len(ent.text.strip()) > 2]
                # combine and deduplicate preserving order
                seen = set()
                combined = []
                for t in (noun_chunks + ents):
                    lt = t.lower()
                    if lt not in seen:
                        seen.add(lt)
                        combined.append(t)

                # Filter combined for emissions-related relevance
                focus = []
                for t in combined:
                    lt = t.lower()
                    if any(k in lt for k in ('emission', 'co2', 'carbon', 'greenhouse', 'methane', 'ghg', 'climate')) or any(c in lt for c in ['china','india','usa','united states','russia','europe','uk']):
                        focus.append(t)

                # If no specific focus found, fall back to top noun chunks
                if not focus:
                    focus = combined[:3]

                # normalize and return up to 3 terms
                res = ' '.join([t for t in focus[:3]])
                logger.debug("extract_terms: method=spacy result=%s", res)
                return res
            except Exception:
                # if spaCy fails for any reason, fall back to heuristics below
                logger.debug('spaCy extraction failed, falling back to heuristics', exc_info=True)

        # --- fallback heuristics (previous implementation) ---
        stopwords = set([
            'the', 'is', 'at', 'which', 'on', 'for', 'and', 'a', 'an', 'of', 'to', 'in', 'that', 'it', 'this',
            'what', 'why', 'how', 'tell', 'me', 'about', 'show', 'give', 'latest', 'recent', 'are', 'be', 'we',
            'i', 'you', 'do', 'does', 'did', 'was', 'were', 'will', 'can', 'please'
        ])

        emissions_terms = set(['co2', 'co₂', 'carbon', 'emissions', 'greenhouse', 'climate', 'methane', 'n2o', 'ghg', 'warming'])
        countries = ['china', 'usa', 'united states', 'india', 'russia', 'japan', 'germany', 'uk', 'united kingdom', 'brazil', 'canada']

        tokens = re.findall(r"\b[\w\-']+\b", q.lower())
        clean = [t for t in tokens if t not in stopwords and len(t) > 2]

        candidates = []
        bigrams = [f"{clean[i]} {clean[i+1]}" for i in range(len(clean)-1)] if len(clean) >= 2 else []
        for bg in bigrams:
            if any(et in bg for et in emissions_terms) or any(c in bg for c in countries) or 'climate' in bg:
                candidates.append(bg)

        for t in clean:
            if t in emissions_terms or t in countries:
                if t not in candidates:
                    candidates.append(t)

        if not candidates:
            for t in clean:
                if 'emission' in t or 'co2' in t or 'carbon' in t or 'climate' in t:
                    candidates.append(t)
            if not candidates:
                candidates = clean[:3]

        if any('emission' in c or 'co2' in c or 'carbon' in c for c in candidates) and 'emissions' not in candidates:
            candidates.append('emissions')

        res = ' '.join(candidates[:3])
        logger.debug("extract_terms: method=heuristic result=%s tokens=%s", res, candidates[:6])
        return res
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return ''


# Global instance
_scraper_instance = None


def get_news_scraper():
    """Get or create the global news scraper instance."""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = NewsScraper()
    return _scraper_instance

