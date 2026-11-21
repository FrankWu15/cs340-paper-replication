package types

import "net/url"

// URLs is a list of URL instances.
type URLs []url.URL

// NewURLs parses a slice of strings into URLs.
func NewURLs(us []string) (URLs, error) {
	urls := make(URLs, len(us))
	for i := range us {
		u, err := url.Parse(us[i])
		if err != nil {
			return nil, err
		}
		urls[i] = *u
	}
	return urls, nil
}
