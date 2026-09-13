using System;

namespace Example.Gen
{
    public interface IHandler5
    {
        bool Handle(string payload);
    }

    public class Base5
    {
        protected string Name;
    }

    public class Service5 : Base5, IHandler5
    {
        public Service5(string name)
        {
            this.Name = name;
        }

        public bool Handle(string payload)
        {
            this.Validate(payload);
            return true;
        }

        private void Validate(string payload) { }
    }
}
