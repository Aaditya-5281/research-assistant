import os
import google.generativeai as genai
from dataclasses import dataclass
from typing import List, Optional
from bs4 import BeautifulSoup
import requests
import time
import arxiv
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

@dataclass
class SearchResult:
    """Data class to store search results"""
    title: str
    link: str = ""
    snippet: str = ""
    body: str = ""
    authors: List[str] = None
    published: str = ""
    abstract: str = ""
    pdf_url: str = ""
    arxiv_url: str = ""
    # Clinical trials specific fields
    nct_id: str = ""
    status: str = ""
    study_type: str = ""
    conditions: List[str] = None
    interventions: List[str] = None
    phase: str = ""
    enrollment: int = 0
    locations: List[str] = None

class SearchTool:
    """Tool for performing Google, arXiv, and ClinicalTrials.gov searches"""
    def __init__(self):
        self.api_key = os.getenv('GOOGLE_API_KEY')
        self.search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

    def google_search(self, query: str, num_results: int = 2, max_chars: int = 500) -> List[SearchResult]:
        """
        Perform Google search and return enriched results
        """
        if not self.api_key or not self.search_engine_id:
            print("Missing API credentials")
            return []

        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": self.api_key,
                "cx": self.search_engine_id,
                "q": query,
                "num": num_results
            }

            response = requests.get(url, params=params)

            if response.status_code != 200:
                print(f"Google Search API error: {response.status_code}")
                print(f"Response content: {response.text}")
                return []

            results = response.json().get("items", [])
            enriched_results = []

            for item in results:
                body = self._get_page_content(item["link"], max_chars)
                result = SearchResult(
                    title=item["title"],
                    link=item["link"],
                    snippet=item["snippet"],
                    body=body
                )
                enriched_results.append(result)
                time.sleep(1)  # Rate limiting

            return enriched_results

        except Exception as e:
            print(f"Error in Google search: {str(e)}")
            return []

    def arxiv_search(self, query: str, max_results: int = 2) -> List[SearchResult]:
        """
        Perform arXiv search and return results
        """
        try:
            client = arxiv.Client()
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance
            )

            results = []
            for paper in client.results(search):
                paper_id = paper.entry_id.split('/')[-1]
                arxiv_url = f"https://arxiv.org/abs/{paper_id}"
                result = SearchResult(
                    title=paper.title,
                    authors=[author.name for author in paper.authors],
                    published=paper.published.strftime("%Y-%m-%d"),
                    abstract=paper.summary,
                    pdf_url=paper.pdf_url,
                    arxiv_url=arxiv_url
                )
                results.append(result)
                time.sleep(0.5)  # Gentle rate limiting

            return results

        except Exception as e:
            print(f"Error in Arxiv search: {str(e)}")
            return []

    def clinicaltrials_search_beta_api(self, query: str, max_results: int = 2) -> List[SearchResult]:
        """
        Perform ClinicalTrials.gov search using their current Beta API
        https://clinicaltrials.gov/data-api/ui
        """
        try:
            # Base URL for the ClinicalTrials.gov Beta API
            base_url = "https://clinicaltrials.gov/api/v2/studies"
            
            # Parameters for the API request
            params = {
                "query.term": query,
                "pageSize": max_results,
                "format": "json"
            }
            
            # Make the API request
            response = requests.get(base_url, params=params, timeout=15)
            
            if response.status_code != 200:
                print(f"ClinicalTrials.gov API error: {response.status_code}")
                print(f"Response content: {response.text}")
                return []
            
            # Parse the JSON response
            data = response.json()
            studies = data.get("studies", [])
            
            if not studies:
                print(f"No clinical trial studies found for query: {query}")
                return []
            
            results = []
            for study in studies:
                # Extract study details
                protocol_section = study.get("protocolSection", {})
                identification = protocol_section.get("identificationModule", {})
                status_module = protocol_section.get("statusModule", {})
                design_module = protocol_section.get("designModule", {})
                conditions_module = protocol_section.get("conditionsModule", {})
                description_module = protocol_section.get("descriptionModule", {})
                
                # Extract NCT ID
                nct_id = identification.get("nctId", "")
                if not nct_id:
                    continue
                
                # Extract title
                title = identification.get("briefTitle", "")
                official_title = identification.get("officialTitle", "")
                
                # Extract study details
                study_type = design_module.get("studyType", "")
                phase_list = design_module.get("phases", [])
                phase = ", ".join(phase_list) if phase_list else "Not Specified"
                
                # Extract status
                status = status_module.get("overallStatus", "")
                
                # Extract conditions
                conditions = conditions_module.get("conditions", [])
                
                # Extract description/summary
                summary = description_module.get("briefSummary", "")
                detailed_desc = description_module.get("detailedDescription", "")
                
                # Create the study URL - using the stable URL format
                # Changed from /study/ to /ct2/show/ which is more stable
                study_url = f"https://clinicaltrials.gov/ct2/show/{nct_id}"
                
                result = SearchResult(
                    title=title if title else official_title,
                    link=study_url,
                    snippet=summary[:200] + "..." if len(summary) > 200 else summary,
                    abstract=summary if summary else detailed_desc,
                    nct_id=nct_id,
                    status=status,
                    study_type=study_type,
                    phase=phase,
                    conditions=conditions
                )
                results.append(result)
                
                # Get full study details if needed
                if not summary and not detailed_desc:
                    detailed_study = self._get_clinical_trial_details_api(nct_id)
                    if detailed_study:
                        result.abstract = detailed_study.abstract
                        result.conditions = detailed_study.conditions
                        result.interventions = detailed_study.interventions
                
                time.sleep(2)  # Increased rate limiting for API requests
                
            return results
            
        except Exception as e:
            print(f"Error in ClinicalTrials.gov Beta API search: {str(e)}")
            return []

    def _get_clinical_trial_details_api(self, nct_id: str) -> Optional[SearchResult]:
        """
        Fetch detailed information for a specific study using the Beta API
        """
        # Validate NCT ID format
        if not nct_id or not nct_id.startswith("NCT"):
            print(f"Invalid NCT ID format: {nct_id}")
            return None
            
        try:
            # Base URL for the ClinicalTrials.gov Beta API - single study endpoint
            base_url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
            
            # Make the API request
            response = requests.get(base_url, params={"format": "json"}, timeout=15)
            
            if response.status_code != 200:
                print(f"ClinicalTrials.gov API error for study {nct_id}: {response.status_code}")
                return None
            
            # Parse the JSON response
            study = response.json()
            
            # Extract study details
            protocol_section = study.get("protocolSection", {})
            identification = protocol_section.get("identificationModule", {})
            description_module = protocol_section.get("descriptionModule", {})
            conditions_module = protocol_section.get("conditionsModule", {})
            intervention_module = protocol_section.get("armsInterventionsModule", {})
            
            # Extract title
            title = identification.get("briefTitle", "")
            
            # Extract summary
            summary = description_module.get("briefSummary", "")
            detailed_desc = description_module.get("detailedDescription", "")
            
            # Extract conditions
            conditions = conditions_module.get("conditions", [])
            
            # Extract interventions
            interventions_list = []
            for intervention in intervention_module.get("interventions", []):
                intervention_name = intervention.get("name", "")
                if intervention_name:
                    interventions_list.append(intervention_name)
            
            # Create the study URL using stable format
            study_url = f"https://clinicaltrials.gov/ct2/show/{nct_id}"
            
            return SearchResult(
                title=title,
                link=study_url,
                nct_id=nct_id,
                abstract=summary if summary else detailed_desc,
                conditions=conditions,
                interventions=interventions_list
            )
            
        except Exception as e:
            print(f"Error fetching details for study {nct_id}: {str(e)}")
            return None

    def clinicaltrials_search_scrape(self, query: str, max_results: int = 2) -> List[SearchResult]:
        """
        Perform ClinicalTrials.gov search by scraping the website
        Use this as a fallback if the API method doesn't work
        """
        try:
            # Construct the search URL - updated to use v2 search
            base_url = "https://clinicaltrials.gov/search"
            params = {
                "term": query,
                "draw": 1,
                "rank": 1
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
            
            # Make the initial request to get the search results page
            response = requests.get(base_url, params=params, headers=headers, timeout=15)
            
            if response.status_code != 200:
                print(f"ClinicalTrials.gov search error: {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.content, "html.parser")
            study_links = soup.select(".ct-search-result a.ct-search-result__title-link")[:max_results]
            
            if not study_links:
                print("No study links found on the search results page")
                return []
            
            results = []
            for link in study_links:
                href = link.get('href', '')
                if not href:
                    continue
                    
                # Extract NCT ID from href and validate
                try:
                    # Different ways the NCT ID might appear in the URL
                    if '/study/' in href:
                        nct_id = href.split('/')[-1]
                    elif '/ct2/show/' in href:
                        nct_id = href.split('/')[-1]
                    else:
                        # Try to find NCT pattern (NCTXXXXXXXX)
                        import re
                        nct_match = re.search(r'(NCT\d{8})', href)
                        if nct_match:
                            nct_id = nct_match.group(1)
                        else:
                            print(f"Could not extract NCT ID from href: {href}")
                            continue
                except Exception as e:
                    print(f"Error extracting NCT ID from {href}: {str(e)}")
                    continue
                
                # Ensure proper URL format
                study_url = f"https://clinicaltrials.gov/ct2/show/{nct_id}"
                
                # Get detailed information from the study page
                study_info = self._get_clinical_trial_details_scrape(study_url)
                if study_info:
                    results.append(study_info)
                    time.sleep(2)  # Increased rate limiting
            
            return results
            
        except Exception as e:
            print(f"Error in ClinicalTrials.gov scrape search: {str(e)}")
            return []

    def _get_clinical_trial_details_scrape(self, url: str) -> Optional[SearchResult]:
        """
        Extract detailed information from a ClinicalTrials.gov study page using web scraping
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5"
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"Error accessing {url}: {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Extract NCT ID - handle different URL formats
            try:
                if '/ct2/show/' in url:
                    nct_id = url.split('/')[-1]
                else:
                    # Try to find NCT pattern
                    import re
                    nct_match = re.search(r'(NCT\d{8})', url)
                    if nct_match:
                        nct_id = nct_match.group(1)
                    else:
                        # Last resort - check the page content for NCT ID
                        nct_elem = soup.find(string=re.compile(r'NCT\d{8}'))
                        if nct_elem:
                            nct_match = re.search(r'(NCT\d{8})', nct_elem)
                            nct_id = nct_match.group(1) if nct_match else "Unknown"
                        else:
                            nct_id = "Unknown"
            except Exception:
                nct_id = "Unknown"
            
            # Extract title - handle different page structures
            title = "Unknown Title"
            title_selectors = ["h1.tr-h1", "h1.ct-title", ".headline-title"]
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text().strip()
                    break
            
            # Extract status
            status = "Unknown"
            status_selectors = [".ct-recruitment-status div.ct-recruitment-status__label", 
                              ".statusLabel", 
                              "p:contains('Recruitment Status:')"]
            for selector in status_selectors:
                status_elem = None
                try:
                    if ':contains' in selector:
                        # Handle custom contains selector
                        text = selector.split(':contains(')[1].strip("')")
                        for p in soup.find_all('p'):
                            if text in p.get_text():
                                status_elem = p
                                break
                    else:
                        status_elem = soup.select_one(selector)
                except Exception:
                    continue
                    
                if status_elem:
                    status_text = status_elem.get_text().strip()
                    if "Status:" in status_text:
                        status = status_text.split("Status:")[1].strip()
                    else:
                        status = status_text
                    break
            
            # Extract summary - try different selectors
            summary = ""
            summary_selectors = ["#brief-summary div.tr-indent2", 
                               ".ct-body__section div.tr-indent1", 
                               "section#brief-summary"]
            for selector in summary_selectors:
                summary_elem = soup.select_one(selector)
                if summary_elem:
                    summary = summary_elem.get_text().strip()
                    break
            
            # Extract study type
            study_type = ""
            study_type_selectors = [
                lambda s: s.find(string="Study Type:"),
                lambda s: s.find("th", string="Study Type")
            ]
            for selector_func in study_type_selectors:
                study_type_label = selector_func(soup)
                if study_type_label:
                    if study_type_label.parent:
                        value_elem = None
                        if study_type_label.parent.name == "th":
                            # Handle table format
                            value_elem = study_type_label.parent.find_next("td")
                        else:
                            # Handle div format
                            value_elem = study_type_label.parent.find_next("div", class_="ct-data-elem__value")
                            if not value_elem:
                                value_elem = study_type_label.parent.find_next_sibling("div")
                        
                        if value_elem:
                            study_type = value_elem.get_text().strip()
                            break
            
            # Extract phase
            phase = ""
            phase_selectors = [
                lambda s: s.find(string="Phase:"),
                lambda s: s.find("th", string="Phase")
            ]
            for selector_func in phase_selectors:
                phase_label = selector_func(soup)
                if phase_label:
                    if phase_label.parent:
                        value_elem = None
                        if phase_label.parent.name == "th":
                            # Handle table format
                            value_elem = phase_label.parent.find_next("td")
                        else:
                            # Handle div format
                            value_elem = phase_label.parent.find_next("div", class_="ct-data-elem__value")
                            if not value_elem:
                                value_elem = phase_label.parent.find_next_sibling("div")
                        
                        if value_elem:
                            phase = value_elem.get_text().strip()
                            break
            
            # Extract conditions
            conditions = []
            conditions_selectors = ["#conditions", "section#conditions", "section:contains('Condition')"]
            for selector in conditions_selectors:
                conditions_section = None
                try:
                    if ':contains' in selector:
                        # Handle custom contains selector
                        text = selector.split(':contains(')[1].strip("')")
                        for section in soup.find_all('section'):
                            if text in section.get_text():
                                conditions_section = section
                                break
                    else:
                        conditions_section = soup.select_one(selector)
                except Exception:
                    continue
                    
                if conditions_section:
                    # Try to find conditions in list items
                    condition_items = conditions_section.select("li")
                    if condition_items:
                        conditions = [item.get_text().strip() for item in condition_items]
                    else:
                        # If no list items, try to get text content
                        conditions_text = conditions_section.get_text().strip()
                        # Remove section title if present
                        if ":" in conditions_text:
                            conditions_text = conditions_text.split(":", 1)[1].strip()
                        conditions = [cond.strip() for cond in conditions_text.split(",")]
                    break
            
            return SearchResult(
                title=title,
                link=url,
                snippet=summary[:200] + "..." if summary and len(summary) > 200 else summary,
                abstract=summary,
                nct_id=nct_id,
                status=status,
                study_type=study_type,
                phase=phase,
                conditions=conditions
            )
            
        except Exception as e:
            print(f"Error extracting details from {url}: {str(e)}")
            return None

    def _get_page_content(self, url: str, max_chars: int) -> str:
        """
        Fetch and extract text content from a webpage
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5"
            }
            response = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()
                
            text = soup.get_text(separator=" ", strip=True)
            return text[:max_chars]
        except Exception as e:
            print(f"Error fetching {url}: {str(e)}")
            return ""

class Agent:
    """AI agent wrapper for Gemini model"""
    def __init__(self, name: str, model: str = "gemini-pro"):
        self.name = name
        self.api_key = os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set")
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(model)
            self.chat = self.model.start_chat(history=[])
        except Exception as e:
            print(f"Error initializing {name}: {str(e)}")
            self.model = None
            self.chat = None

    async def process(self, message: str) -> str:
        """
        Process a message using the Gemini model
        """
        if not self.chat:
            return "Error: Agent not properly initialized"
        try:
            response = self.chat.send_message(message)
            return response.text
        except Exception as e:
            print(f"Error processing message: {str(e)}")
            return f"Error processing message: {str(e)}"

class MultiAgentSystem:
    """
    System coordinating multiple agents for literature review
    """
    def __init__(self):
        self.google_agent = Agent("Google_Search_Agent")
        self.arxiv_agent = Agent("Arxiv_Search_Agent")
        self.clinical_trials_agent = Agent("ClinicalTrials_Search_Agent")
        self.report_agent = Agent("Report_Agent")
        self.search_tool = SearchTool()

    async def run_literature_review(self, topic: str) -> str:
        """
        Run a comprehensive literature review on a given topic
        """
        # Step 1: Google Search
        print(f"Performing Google search for '{topic}'...")
        google_results = self.search_tool.google_search(topic)
        google_context = f"Based on Google search for '{topic}', here are the findings:\n"
        if google_results:
            for result in google_results:
                google_context += f"\nTitle: {result.title}\nSnippet: {result.snippet}\nContent: {result.body[:500]}...\n"
        else:
            google_context += "\nNo Google search results found.\n"

        # Step 2: Arxiv Search
        print(f"Performing Arxiv search for '{topic}'...")
        arxiv_results = self.search_tool.arxiv_search(topic)
        arxiv_context = f"\nBased on Arxiv search for '{topic}', here are the academic papers:\n"
        if arxiv_results:
            for result in arxiv_results:
                authors = result.authors if result.authors else []
                arxiv_context += (f"\nTitle: {result.title}\n"
                                f"Authors: {', '.join(authors)}\n"
                                f"Published: {result.published}\n"
                                f"Abstract: {result.abstract}\n"
                                f"URL: {result.arxiv_url}\n")
        else:
            arxiv_context += "\nNo Arxiv papers found.\n"
        
        # Step 3: ClinicalTrials.gov Search 
        print(f"Performing ClinicalTrials.gov search for '{topic}'...")
        # Try Beta API first, then fall back to scraping if needed
        clinical_trials_results = self.search_tool.clinicaltrials_search_beta_api(topic)
        if not clinical_trials_results:
            print("API search failed, falling back to scrape method...")
            clinical_trials_results = self.search_tool.clinicaltrials_search_scrape(topic)
            
        clinical_trials_context = f"\nBased on ClinicalTrials.gov search for '{topic}', here are the clinical trials:\n"
        if clinical_trials_results:
            for result in clinical_trials_results:
                conditions_list = result.conditions if result.conditions else []
                clinical_trials_context += (f"\nTitle: {result.title}\n"
                                            f"NCT ID: {result.nct_id}\n"
                                            f"Status: {result.status}\n"
                                            f"Study Type: {result.study_type}\n"
                                            f"Phase: {result.phase}\n"
                                            f"Conditions: {', '.join(conditions_list) if conditions_list else 'Not specified'}\n"
                                            f"Summary: {result.abstract[:300]}...\n"
                                            f"URL: {result.link}\n")
        else:
            clinical_trials_context += "\nNo clinical trials found.\n"

        # Step 4: Generate Report
        print("Generating comprehensive literature review report...")
        report_prompt = f"""
        Generate a comprehensive literature review on {topic} based on the following sources:

        {google_context}

        {arxiv_context}

        {clinical_trials_context}

        Please provide a well-structured literature review that:
        1. Synthesizes the main findings and themes
        2. Identifies key research directions
        3. Includes proper citations with clickable links
        4. Concludes with future research directions

        Important links to include:
        - ClinicalTrials.gov links with NCT IDs should use format: https://clinicaltrials.gov/ct2/show/NCTXXXXXXXX 
        - arXiv links for academic papers

        For the References section, use these exact formats:
        For arXiv papers: Author(s), "Title", [arXiv:XXXX.XXXXX](https://arxiv.org/abs/XXXX.XXXXX)
        For clinical trials: "Title", [NCT ID: NCTXXXXXXXX](https://clinicaltrials.gov/ct2/show/NCTXXXXXXXX)

        If no results were found in a particular source, please mention that in your review.
        """

        report = await self.report_agent.process(report_prompt)
        return report

# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def run_literature_review():
        system = MultiAgentSystem()
        topic = input("Enter a medical or scientific topic for literature review: ")
        print(f"\nRunning comprehensive literature review on: {topic}")
        print("This may take a few minutes...\n")
        
        report = await system.run_literature_review(topic)
        print("\n" + "="*80)
        print("LITERATURE REVIEW REPORT")
        print("="*80 + "\n")
        print(report)
        
        # Save report to file
        filename = f"literature_review_{topic.replace(' ', '_')}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nReport saved to {filename}")
    
    async def test_search():
        search_tool = SearchTool()
        query = input("Enter a medical topic to test search: ")
        
        print("\nTesting ClinicalTrials.gov Beta API search...")
        api_results = search_tool.clinicaltrials_search_beta_api(query, max_results=2)
        for result in api_results:
            print(f"Title: {result.title}")
            print(f"NCT ID: {result.nct_id}")
            print(f"URL: {result.link}")
            print(f"Status: {result.status}")
            print(f"Phase: {result.phase}")
            print(f"Conditions: {result.conditions}")
            print("-" * 50)
        
        print("\nTesting ClinicalTrials.gov scrape search (fallback method)...")
        scrape_results = search_tool.clinicaltrials_search_scrape(query, max_results=2)
        for result in scrape_results:
            print(f"Title: {result.title}")
            print(f"NCT ID: {result.nct_id}")
            print(f"URL: {result.link}")
            print(f"Status: {result.status}")
            print("-" * 50)
    
    # Choose which function to run
    choice = input("Choose an option:\n1. Run full literature review\n2. Test search only\nYour choice (1/2): ")
    if choice == "1":
        asyncio.run(run_literature_review())
    else:
        asyncio.run(test_search())