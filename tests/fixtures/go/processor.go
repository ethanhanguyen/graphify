// processor.go — data processing core with interfaces and inheritance via embedding

package fixtures

// ProcessorConfig holds pipeline configuration
type ProcessorConfig struct {
	RequiredFields []string
	Strict         bool
}

// Transformer applies a transformation to data
type Transformer interface {
	Transform(data map[string]interface{}) map[string]interface{}
}

// DataProcessor is the base pipeline processor
type DataProcessor struct {
	config       ProcessorConfig
	transformers []Transformer
}

// NewDataProcessor creates a new processor with the given config
func NewDataProcessor(cfg ProcessorConfig) *DataProcessor {
	return &DataProcessor{config: cfg}
}

// AddTransformer appends a transformer to the pipeline
func (p *DataProcessor) AddTransformer(t Transformer) {
	p.transformers = append(p.transformers, t)
}

// Process runs all transformers in sequence
func (p *DataProcessor) Process(data map[string]interface{}) map[string]interface{} {
	result := make(map[string]interface{})
	for k, v := range data {
		result[k] = v
	}
	for _, t := range p.transformers {
		result = t.Transform(result)
	}
	return result
}

// Validate checks that required fields are present
func (p *DataProcessor) Validate(data map[string]interface{}) bool {
	for _, f := range p.config.RequiredFields {
		if _, ok := data[f]; !ok {
			return false
		}
	}
	return true
}
