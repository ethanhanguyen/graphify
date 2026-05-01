// pipeline.go — entry point composing processor and filters

package fixtures

// PipelineConfig selects the pipeline configuration
type PipelineConfig struct {
	mode string
}

// NewPipelineConfig creates a config with the given mode
func NewPipelineConfig(mode string) *PipelineConfig {
	return &PipelineConfig{mode: mode}
}

// BuildPipeline constructs the appropriate processor for the mode
func (pc *PipelineConfig) BuildPipeline() *DataProcessor {
	cfg := ProcessorConfig{RequiredFields: []string{"id", "name"}}
	proc := NewDataProcessor(cfg)
	proc.AddTransformer(NormalizeFilter{})
	proc.AddTransformer(RemoveNullFilter{})
	return proc
}

// RunPipeline processes a batch of records
func RunPipeline(inputData []map[string]interface{}) []map[string]interface{} {
	pc := NewPipelineConfig("default")
	proc := pc.BuildPipeline()
	result := make([]map[string]interface{}, len(inputData))
	for i, d := range inputData {
		result[i] = proc.Process(d)
	}
	return result
}
