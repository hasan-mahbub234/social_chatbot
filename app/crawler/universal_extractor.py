"""Universal content extractor — multi-pass: JSON-LD → OG → trafilatura → platform → AI fallback."""
import re
import json
from typing import Dict, Any, Optional, Tuple, List
from app.core.logging import get_logger

logger = get_logger(__name__)


class UniversalExtractor:
    """
    Multi-pass extraction pipeline:
    PASS 1: JSON-LD / Schema.org / OpenGraph / Meta tags
    PASS 2: Semantic DOM extraction (tables, FAQs, accordions, tabs, hidden sections)
    PASS 3: Platform-specific extraction (Shopify, WooCommerce, WordPress, Magento, Next.js, GitBook, Zendesk)
    PASS 4: trafilatura / readability fallback
    PASS 5: AI-assisted extraction (low-confidence fallback)
    """

    def extract(self, html: str, url: str = "") -> Dict[str, Any]:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            platform = self._detect_platform(soup, html, url)
            og = self._extract_og(soup)

            # PASS 0: Hydration state (Next.js / Nuxt / Shopify window state)
            # Runs before JSON-LD because hydration state is often more complete
            try:
                from app.crawler.hydration_extractor import hydration_extractor
                hydration_data = hydration_extractor.extract(html, url)
                if hydration_data and hydration_data.get("title") and hydration_data.get("price"):
                    from app.crawler.entity_model import ProductEntity
                    entity = ProductEntity(url=url)
                    entity.merge("hydration", hydration_data)
                    content = entity.to_content_string()
                    if len(content) > 150:
                        semantic = self._extract_semantic_dom(soup)
                        if semantic:
                            content += "\n\n" + semantic
                        return {
                            "title": hydration_data.get("title", ""),
                            "content": content,
                            "content_type": "product",
                            "platform": platform,
                            "extraction_source": "hydration",
                        }
            except Exception:
                pass

            # PASS 1: JSON-LD
            jsonld = self._extract_jsonld(soup)
            if jsonld:
                result = self._normalize_jsonld(jsonld, url)
                if result and len(result.get("content", "")) > 100:
                    result["platform"] = platform
                    # Augment with semantic DOM content
                    semantic = self._extract_semantic_dom(soup)
                    if semantic:
                        result["content"] = result["content"] + "\n\n" + semantic
                    return result

            # PASS 2: Platform-specific
            platform_result = self._extract_by_platform(soup, html, url, platform, og)
            if platform_result and len(platform_result.get("content", "")) > 150:
                semantic = self._extract_semantic_dom(soup)
                if semantic:
                    platform_result["content"] += "\n\n" + semantic
                return platform_result

            # PASS 3: trafilatura
            trafilatura_result = self._extract_with_trafilatura(html, url)
            if trafilatura_result and len(trafilatura_result.get("content", "")) > 200:
                trafilatura_result["platform"] = platform
                return trafilatura_result

            # PASS 4: readability
            readability_result = self._extract_with_readability(html, url)
            if readability_result and len(readability_result.get("content", "")) > 200:
                readability_result["platform"] = platform
                return readability_result

            # PASS 5: Generic density-based
            return self._extract_generic(soup, og, platform)

        except Exception as e:
            logger.error("universal_extractor_failed", url=url, error=str(e))
            return {"title": "", "content": "", "content_type": "generic", "platform": "generic"}

    # ── Platform detection ────────────────────────────────────────────────
    def _detect_platform(self, soup, html: str, url: str) -> str:
        if "Shopify.theme" in html or "/cdn/shop/" in html:
            return "shopify"
        if "woocommerce" in html.lower() or "wp-content/plugins/woocommerce" in html:
            return "woocommerce"
        if "wp-content" in html or "wp-includes" in html:
            return "wordpress"
        if "__next_f" in html or "_next/static" in html:
            return "nextjs"
        if "Magento" in html or "mage/cookies" in html:
            return "magento"
        if "gitbook" in html.lower() or "gitbook.io" in url:
            return "gitbook"
        if "zendesk" in html.lower() or "zendesk.com" in url:
            return "zendesk"
        if "discourse" in html.lower() or "discourse-cdn" in html:
            return "discourse"
        generator = soup.find("meta", attrs={"name": "generator"})
        if generator:
            g = generator.get("content", "").lower()
            if "wordpress" in g:
                return "wordpress"
        return "generic"

    # ── JSON-LD extraction ────────────────────────────────────────────────
    def _extract_jsonld(self, soup) -> Optional[Dict]:
        priority = ["Product", "Article", "BlogPosting", "NewsArticle", "FAQPage",
                    "LocalBusiness", "Restaurant", "Event", "Organization", "WebPage"]
        blocks = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if "@graph" in data:
                    blocks.extend(data["@graph"])
                elif isinstance(data, list):
                    blocks.extend(data)
                else:
                    blocks.append(data)
            except Exception:
                continue
        for p in priority:
            for b in blocks:
                if b.get("@type") == p:
                    return b
        return blocks[0] if blocks else None

    def _normalize_jsonld(self, data: Dict, url: str) -> Optional[Dict]:
        t = data.get("@type", "")
        if t == "Product":
            return self._from_product_schema(data)
        if t in ("Article", "BlogPosting", "NewsArticle"):
            return self._from_article_schema(data)
        if t == "FAQPage":
            return self._from_faq_schema(data)
        if t in ("LocalBusiness", "Restaurant"):
            return self._from_business_schema(data, is_restaurant=(t == "Restaurant"))
        if t == "Event":
            return self._from_event_schema(data)
        return None

    def _from_product_schema(self, d: Dict) -> Dict:
        lines = [f"Product: {d.get('name', '')}"]
        offers = d.get("offers", [])
        if isinstance(offers, dict):
            offers = [offers]
        if offers:
            prices = list({float(o.get("price", 0)) for o in offers if o.get("price")})
            currency = offers[0].get("priceCurrency", "")
            if prices:
                price_str = f"{min(prices):.2f}" if len(set(prices)) == 1 else f"{min(prices):.2f} - {max(prices):.2f}"
                lines.append(f"Price: {price_str} {currency}")
            avail = offers[0].get("availability", "")
            if "InStock" in avail:
                lines.append("Availability: In Stock")
            elif "OutOfStock" in avail:
                lines.append("Availability: Out of Stock")
        brand = d.get("brand", {})
        if isinstance(brand, dict):
            brand = brand.get("name", "")
        if brand:
            lines.append(f"Brand: {brand}")
        if d.get("sku"):
            lines.append(f"SKU: {d['sku']}")
        desc = self._clean_html(d.get("description", ""))
        if desc:
            lines.append(f"\nDescription:\n{desc}")
        for field in ("material", "color", "size", "weight", "category"):
            if d.get(field):
                lines.append(f"{field.capitalize()}: {d[field]}")
        return {"title": d.get("name", ""), "content": "\n".join(lines), "content_type": "product"}

    def _from_article_schema(self, d: Dict) -> Dict:
        lines = [f"Title: {d.get('name') or d.get('headline', '')}"]
        author = d.get("author", {})
        if isinstance(author, dict):
            author = author.get("name", "")
        if author:
            lines.append(f"Author: {author}")
        date = d.get("datePublished", "") or d.get("dateModified", "")
        if date:
            lines.append(f"Published: {date[:10]}")
        desc = self._clean_html(d.get("description", "") or d.get("articleBody", ""))
        if desc:
            lines.append(f"\n{desc}")
        return {"title": d.get("name") or d.get("headline", ""), "content": "\n".join(lines), "content_type": "article"}

    def _from_faq_schema(self, d: Dict) -> Dict:
        lines = ["FAQ:"]
        for item in d.get("mainEntity", []):
            q = item.get("name", "")
            a = self._clean_html(item.get("acceptedAnswer", {}).get("text", ""))
            if q and a:
                lines.append(f"Q: {q}\nA: {a}")
        return {"title": "FAQ", "content": "\n\n".join(lines), "content_type": "faq"}

    def _from_business_schema(self, d: Dict, is_restaurant: bool = False) -> Dict:
        label = "Restaurant" if is_restaurant else "Business"
        lines = [f"{label}: {d.get('name', '')}"]
        addr = d.get("address", {})
        if isinstance(addr, dict):
            parts = [addr.get(k, "") for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")]
            addr_str = ", ".join(p for p in parts if p)
            if addr_str:
                lines.append(f"Address: {addr_str}")
        if d.get("telephone"):
            lines.append(f"Phone: {d['telephone']}")
        if d.get("openingHours"):
            lines.append(f"Hours: {d['openingHours']}")
        if is_restaurant and d.get("servesCuisine"):
            lines.append(f"Cuisine: {d['servesCuisine']}")
        if d.get("priceRange"):
            lines.append(f"Price Range: {d['priceRange']}")
        desc = self._clean_html(d.get("description", ""))
        if desc:
            lines.append(f"\n{desc}")
        return {"title": d.get("name", ""), "content": "\n".join(lines), "content_type": "restaurant" if is_restaurant else "business"}

    def _from_event_schema(self, d: Dict) -> Dict:
        lines = [f"Event: {d.get('name', '')}"]
        if d.get("startDate"):
            lines.append(f"Date: {d['startDate'][:10]}")
        location = d.get("location", {})
        if isinstance(location, dict) and location.get("name"):
            lines.append(f"Location: {location['name']}")
        price = d.get("offers", {})
        if isinstance(price, dict) and price.get("price"):
            lines.append(f"Price: {price['price']}")
        desc = self._clean_html(d.get("description", ""))
        if desc:
            lines.append(f"\n{desc}")
        return {"title": d.get("name", ""), "content": "\n".join(lines), "content_type": "event"}

    # ── Semantic DOM extraction (tables, FAQs, accordions, hidden sections) ──
    def _extract_semantic_dom(self, soup) -> str:
        """Extract tables, FAQ pairs, accordions, tabs, and hidden semantic sections."""
        sections = []

        # Tables → pipe-delimited text
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                sections.append("\n".join(rows))

        # Accordions / details+summary (DO NOT skip hidden content)
        for details in soup.find_all("details"):
            summary = details.find("summary")
            label = summary.get_text(strip=True) if summary else ""
            body_parts = []
            for child in details.children:
                if child == summary:
                    continue
                text = child.get_text(strip=True) if hasattr(child, "get_text") else str(child).strip()
                if text:
                    body_parts.append(text)
            body = " ".join(body_parts)
            if label and body:
                sections.append(f"Q: {label}\nA: {body}")

        # FAQ-like divs (class contains faq/accordion)
        for el in soup.find_all(class_=re.compile(r'faq|accordion|collapse', re.I)):
            q_el = el.find(re.compile(r'h[1-6]|dt|button|summary'))
            a_el = el.find(re.compile(r'p|dd|div'))
            if q_el and a_el:
                q = q_el.get_text(strip=True)
                a = a_el.get_text(strip=True)
                if q and a and q != a:
                    sections.append(f"Q: {q}\nA: {a}")

        # Tab panels (keep hidden tab content)
        for panel in soup.find_all(attrs={"role": "tabpanel"}):
            text = panel.get_text(separator="\n", strip=True)
            if len(text) > 50:
                sections.append(text)

        return "\n\n".join(s for s in sections if s)

    # ── Open Graph extraction ────────────────────────────────────────────
    def _extract_og(self, soup) -> Dict[str, str]:
        og = {}
        for m in soup.find_all("meta"):
            prop = m.get("property", "") or m.get("name", "")
            content = m.get("content", "")
            if content and (prop.startswith("og:") or prop.startswith("product:")):
                key = prop.replace("og:", "").replace("product:", "")
                og[key] = content
        return og

    # ── Platform-specific extraction ─────────────────────────────────────
    def _extract_by_platform(self, soup, html: str, url: str, platform: str, og: Dict) -> Optional[Dict]:
        h1 = soup.find("h1")
        title = (h1.get_text(strip=True) if h1
                 else og.get("title", "")
                 or (soup.title.string.strip() if soup.title else ""))

        content, content_type = "", "page"
        if platform == "woocommerce":
            content, content_type = self._extract_woocommerce(soup)
        elif platform == "wordpress":
            content, content_type = self._extract_wordpress(soup)
        elif platform == "shopify":
            content, content_type = self._extract_shopify_html(soup, url)
        elif platform == "magento":
            content, content_type = self._extract_magento(soup)
        elif platform in ("gitbook", "zendesk", "discourse"):
            content, content_type = self._extract_docs(soup)
        elif platform == "nextjs":
            content, content_type = self._extract_nextjs(soup)
        else:
            content, content_type = self._extract_generic_html(soup, og)

        if not content:
            return None
        if title and not content.startswith(title):
            content = f"{title}\n{content}"
        return {"title": title, "content": content, "content_type": content_type, "platform": platform}

    def _extract_woocommerce(self, soup) -> Tuple[str, str]:
        lines = []
        summary = soup.find("div", class_=lambda c: c and "summary" in c) or soup
        price_p = (summary.find("p", class_="price") or soup.find("p", class_="price")
                   or summary.find("span", class_="price") or soup.find("span", class_="price"))
        if price_p:
            bdis = [b.get_text(strip=True) for b in price_p.find_all("bdi")]
            nums = [re.sub(r'[^\d,.]', '', b) for b in bdis if re.search(r'\d', b)]
            if len(nums) >= 2:
                lines.append(f"Price: {nums[0]}৳ - {nums[-1]}৳")
            elif nums:
                lines.append(f"Price: {nums[0]}৳")
            else:
                lines.append(f"Price: {price_p.get_text(strip=True)}")
        for tab in soup.find_all(["div", "section"], class_=lambda c: c and any(
                k in (c or "") for k in ["description", "product-details", "woocommerce-tabs"])):
            text = tab.get_text(separator="\n", strip=True)
            if len(text) > 50:
                lines.append(text[:3000])
                break
        for table in soup.find_all("table", class_=lambda c: c and "attribute" in (c or "")):
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) == 2:
                    lines.append(f"{cells[0].get_text(strip=True)}: {cells[1].get_text(strip=True)}")
        return "\n".join(lines), "product"

    def _extract_wordpress(self, soup) -> Tuple[str, str]:
        for selector in [".entry-content", ".post-content", ".article-content",
                         "article", "main .content", ".page-content"]:
            el = soup.select_one(selector)
            if el:
                for tag in el(["script", "style", "nav", "aside"]):
                    tag.decompose()
                return el.get_text(separator="\n", strip=True)[:4000], "article"
        return self._extract_generic_html(soup, {})

    def _extract_shopify_html(self, soup, url: str) -> Tuple[str, str]:
        article = soup.find("article") or soup.find("div", class_=lambda c: c and "article" in (c or ""))
        if article:
            for tag in article(["script", "style"]):
                tag.decompose()
            return article.get_text(separator="\n", strip=True)[:4000], "article"
        return self._extract_generic_html(soup, {})

    def _extract_magento(self, soup) -> Tuple[str, str]:
        for selector in [".product-info-main", ".product.attribute.description", ".product-details"]:
            el = soup.select_one(selector)
            if el:
                return el.get_text(separator="\n", strip=True)[:4000], "product"
        return self._extract_generic_html(soup, {})

    def _extract_docs(self, soup) -> Tuple[str, str]:
        for selector in ["article", "main", ".content", ".markdown-body", ".article-body"]:
            el = soup.select_one(selector)
            if el:
                for tag in el(["script", "style", "nav"]):
                    tag.decompose()
                return el.get_text(separator="\n", strip=True)[:5000], "documentation"
        return self._extract_generic_html(soup, {})

    def _extract_nextjs(self, soup) -> Tuple[str, str]:
        main = soup.find("main") or soup.find(id="__next")
        if main:
            for tag in main(["script", "style", "nav"]):
                tag.decompose()
            return main.get_text(separator="\n", strip=True)[:4000], "page"
        return self._extract_generic_html(soup, {})

    def _extract_generic_html(self, soup, og: Dict) -> Tuple[str, str]:
        if og.get("price:amount") or og.get("sale_price"):
            title = og.get("title", "")
            price = og.get("sale_price") or og.get("price:amount", "")
            currency = og.get("price:currency", "")
            brand = og.get("brand", "")
            availability = og.get("availability", "")
            desc = og.get("description", "")
            lines = [f"Product: {title}"]
            if price:
                lines.append(f"Price: {price} {currency}".strip())
            if brand:
                lines.append(f"Brand: {brand}")
            if availability:
                lines.append(f"Availability: {availability}")
            if desc:
                lines.append(f"Description: {desc}")
            return "\n".join(lines), "product"

        for tag in soup(["script", "style", "noscript", "nav", "footer",
                         "header", "aside", "form", "iframe"]):
            tag.decompose()

        for selector in ["main", "article", "section"]:
            el = soup.find(selector)
            if el and len(el.get_text(strip=True)) > 200:
                return el.get_text(separator="\n", strip=True)[:4000], "page"

        # Text density scoring
        best, best_score = None, 0
        for div in soup.find_all(["div", "main", "article", "section"]):
            text = div.get_text(strip=True)
            if len(text) < 100:
                continue
            links = div.find_all("a")
            link_density = len(" ".join(a.get_text() for a in links)) / max(len(text), 1)
            score = len(text) * (1 - link_density)
            if score > best_score:
                best_score = score
                best = div
        if best:
            return best.get_text(separator="\n", strip=True)[:4000], "page"

        return soup.get_text(separator="\n", strip=True)[:2000], "page"

    # ── trafilatura extraction ────────────────────────────────────────────
    def _extract_with_trafilatura(self, html: str, url: str) -> Optional[Dict]:
        try:
            import trafilatura
            text = trafilatura.extract(
                html,
                include_tables=True,
                include_links=False,
                include_comments=False,
                favor_precision=False,
                favor_recall=True,
                url=url,
            )
            if text and len(text) > 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                title = soup.title.string.strip() if soup.title else ""
                return {"title": title, "content": text, "content_type": "article"}
        except ImportError:
            pass
        except Exception as e:
            logger.debug("trafilatura_failed", url=url, error=str(e))
        return None

    # ── readability fallback ─────────────────────────────────────────────
    def _extract_with_readability(self, html: str, url: str) -> Optional[Dict]:
        try:
            import logging as _logging
            _logging.getLogger("readability").setLevel(_logging.ERROR)
            from readability import Document
            doc = Document(html)
            content_html = doc.summary()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(content_html, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return {"title": doc.title(), "content": text, "content_type": "article"}
        except ImportError:
            pass
        except Exception as e:
            logger.debug("readability_failed", url=url, error=str(e))
        return None

    # ── Generic density fallback ─────────────────────────────────────────
    def _extract_generic(self, soup, og: Dict, platform: str) -> Dict:
        content, content_type = self._extract_generic_html(soup, og)
        h1 = soup.find("h1")
        title = (h1.get_text(strip=True) if h1
                 else og.get("title", "")
                 or (soup.title.string.strip() if soup.title else ""))
        return {"title": title, "content": content, "content_type": content_type, "platform": platform}

    def _clean_html(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&nbsp;", " ", text)
        return re.sub(r"\s{2,}", " ", text).strip()


universal_extractor = UniversalExtractor()
