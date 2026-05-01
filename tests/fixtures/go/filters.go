// filters.go — transformer implementations

package fixtures

import "strings"

// NormalizeFilter strips and lowercases string values
type NormalizeFilter struct{}

func (f NormalizeFilter) Transform(data map[string]interface{}) map[string]interface{} {
	result := make(map[string]interface{})
	for k, v := range data {
		if s, ok := v.(string); ok {
			result[k] = strings.ToLower(strings.TrimSpace(s))
		} else {
			result[k] = v
		}
	}
	return result
}

// RemoveNullFilter removes nil values
type RemoveNullFilter struct{}

func (f RemoveNullFilter) Transform(data map[string]interface{}) map[string]interface{} {
	result := make(map[string]interface{})
	for k, v := range data {
		if v != nil {
			result[k] = v
		}
	}
	return result
}

// ChainFilters composes multiple transformers into one
func ChainFilters(filters ...Transformer) Transformer {
	return &chainTransformer{filters: filters}
}

type chainTransformer struct {
	filters []Transformer
}

func (c *chainTransformer) Transform(data map[string]interface{}) map[string]interface{} {
	r := data
	for _, f := range c.filters {
		r = f.Transform(r)
	}
	return r
}
